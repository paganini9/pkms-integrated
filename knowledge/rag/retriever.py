"""Chroma 기반 검색기 — 하이브리드(임베딩) 검색 + 충분성 판단.

`interface_contracts.md` §2 `Retriever` Protocol 구현.
- 메타데이터에 RDF IRI·about_symptom·derives_rule·category·문장 코드를 저장(검색→온톨로지 연결).
- 점수는 코사인 거리 → 유사도(0~1, 클수록 유사)로 변환.
- IRI 를 chroma id 로 사용(트리플스토어와 동기·멱등 upsert).
- `project_id` 가 주어지면 그 프로젝트의 카테고리로 검증 범위를 제한(ProjectScopeProvider).

import 부작용 금지: 모듈 최상단에서 Chroma 를 열지 않는다(생성자에서만 연다).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

from core.config import settings
from schemas.models import RagHit

from .embedder import get_embedder
from .sources import SentenceRecord, SentenceSource, TtlSentenceSource
from .verifier import MockRuleVerifier, RuleVerifier

log = logging.getLogger("rag.retriever")

COLLECTION = "knowledge_sentences"


# ── 프로젝트 지식범위 공급자 ────────────────────────────────────────────────
@runtime_checkable
class ProjectScopeProvider(Protocol):
    def categories_for(self, project_id: str | None) -> set[str] | None: ...


class MockProjectScopeProvider:
    """06 프로젝트 API 미완 시 기본 매핑. 미등록 프로젝트는 None(필터 없음)."""

    DEFAULT = {
        "proj-winter-suv": {"소음", "떨림"},
        "proj-vibration-lab": {"떨림"},
    }

    def __init__(self, mapping: dict[str, set[str]] | None = None) -> None:
        self.mapping = mapping or dict(self.DEFAULT)

    def categories_for(self, project_id: str | None) -> set[str] | None:
        if not project_id:
            return None
        return self.mapping.get(project_id)


def _clean_meta(rec: SentenceRecord) -> dict[str, str]:
    """Chroma 메타데이터는 None 을 허용하지 않는다 → 빈 문자열로 대체."""
    return {
        "iri": rec.iri,
        "sentence": rec.code,
        "category": rec.category or "",
        "about_symptom": rec.about_symptom or "",
        "derives_rule": rec.derives_rule or "",
    }


class ChromaRetriever:
    def __init__(
        self,
        embedder=None,  # noqa: ANN001
        source: SentenceSource | None = None,
        verifier: RuleVerifier | None = None,
        scope_provider: ProjectScopeProvider | None = None,
        chroma_path: Path | None = None,
        collection_name: str = COLLECTION,
    ) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.embedder = embedder or get_embedder()
        self.source = source or TtlSentenceSource()
        if verifier is None:
            known = (
                self.source.known_rules()
                if hasattr(self.source, "known_rules")
                else {}
            )
            verifier = MockRuleVerifier(known)
        self.verifier = verifier
        self.scope = scope_provider or MockProjectScopeProvider()

        path = Path(chroma_path or settings.chroma_path)
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        # 코사인 공간: 거리 ∈ [0,2], 유사도 = 1 - 거리
        self._col = self._client.get_or_create_collection(
            collection_name, metadata={"hnsw:space": "cosine"}
        )

    # ── 인덱싱 ───────────────────────────────────────────────────────────
    def ensure_indexed(self) -> int:
        """최초 1회 SentenceSource 로 초기 인덱싱(멱등: 같은 IRI 는 upsert)."""
        records = self.source.sentences()
        if not records:
            return self._col.count()
        # IRI 가 id 이므로 재호출해도 컬렉션 크기가 불변(멱등)
        texts = [r.text for r in records]
        embeddings = self.embedder.encode(texts)
        self._col.upsert(
            ids=[r.iri for r in records],
            embeddings=embeddings,
            documents=texts,
            metadatas=[_clean_meta(r) for r in records],
        )
        return self._col.count()

    # ── 검색 ─────────────────────────────────────────────────────────────
    def search(
        self, query: str, k: int = 6, project_id: str | None = None
    ) -> list[RagHit]:
        categories = self.scope.categories_for(project_id) if project_id else None
        if self._col.count() == 0:
            self.ensure_indexed()

        qvec = self.embedder.encode([query])[0]
        n = min(k, max(self._col.count(), 1))
        res = self._col.query(
            query_embeddings=[qvec],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        hits: list[RagHit] = []
        for doc, meta, dist in zip(docs, metas, dists):
            meta = meta or {}
            rule_id = meta.get("derives_rule") or None
            verified = self.verifier.is_verified(rule_id, categories)
            hits.append(
                RagHit(
                    iri=meta.get("iri", ""),
                    text=doc or "",
                    score=_distance_to_similarity(dist),
                    verified=verified,
                    sentence=meta.get("sentence") or None,
                    about_symptom=meta.get("about_symptom") or None,
                    derives_rule=rule_id,
                )
            )
        return hits

    def is_sufficient(self, hits: list[RagHit]) -> bool:
        """verified=True hit 가 1건 이상이어야 충분(미검증 근거 0)."""
        return any(h.verified for h in hits)

    # ── 동기화 ───────────────────────────────────────────────────────────
    def upsert(self, items: list[dict]) -> int:
        """items: {iri, text, category?, about_symptom?, derives_rule?, sentence?, embedding?}"""
        if not items:
            return 0
        ids, docs, metas, embs = [], [], [], []
        need_embed = []
        for it in items:
            iri = it["iri"]
            text = it.get("text", "")
            ids.append(iri)
            docs.append(text)
            metas.append(
                {
                    "iri": iri,
                    "sentence": it.get("sentence") or "",
                    "category": it.get("category") or "",
                    "about_symptom": it.get("about_symptom") or "",
                    "derives_rule": it.get("derives_rule") or "",
                }
            )
            if it.get("embedding") is not None:
                embs.append(it["embedding"])
            else:
                embs.append(None)
                need_embed.append((len(embs) - 1, text))
        if need_embed:
            computed = self.embedder.encode([t for _, t in need_embed])
            for (idx, _), vec in zip(need_embed, computed):
                embs[idx] = vec
        self._col.upsert(ids=ids, embeddings=embs, documents=docs, metadatas=metas)
        return len(ids)

    def delete(self, iris: list[str]) -> int:
        if not iris:
            return 0
        self._col.delete(ids=iris)
        return len(iris)

    def count(self) -> int:
        return self._col.count()


def _distance_to_similarity(dist: float | None) -> float:
    """코사인 거리(0~2) → 유사도(0~1). 클수록 유사. 범위 밖 값은 클램프."""
    if dist is None:
        return 0.0
    sim = 1.0 - float(dist)
    if sim < 0.0:
        return 0.0
    if sim > 1.0:
        return 1.0
    return sim
