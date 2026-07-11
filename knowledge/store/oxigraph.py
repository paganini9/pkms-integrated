"""Oxigraph 임베디드 영속 스토어 — `core.protocols.Store` 구현.

- pyoxigraph 를 트리플 저장의 단일 엔진으로 쓴다(임베디드·영속).
- 시드 TTL 은 **파일별 named graph** 에 적재하고, 재적재 시 그 그래프만 CLEAR 후 다시 읽어
  블랭크노드가 있어도 **멱등** 하다. (블랭크노드는 매 적재마다 새 id 를 받으므로,
  단순히 default graph 에 두 번 load 하면 트리플이 늘어난다 — named graph + clear 가 해법.)
- 조회는 `use_default_graph_as_union=True` 로 모든 그래프(시드 + 저장분)를 함께 본다.
- reasoner(04) 입력용 `subgraph()`/`to_rdflib()` 는 pyoxigraph 항을 rdflib 항으로
  **직접 변환** 한다(oxrdflib 미사용 — 사유는 모듈 하단 참고).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pyoxigraph as ox

from schemas.errors import ValidationError
from schemas.models import SavedSentence
from store import sparql as _gate

if TYPE_CHECKING:
    from rdflib import Graph

# 네임스페이스
DOM = "http://ex.org/domain#"
EXT = "http://ex.org/spmm-ext#"
SPMM = "http://ex.org/spmm#"
ENG = "http://ex.org/eng#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
XSD_DATETIME = "http://www.w3.org/2001/XMLSchema#dateTime"
CREATED_AT = f"{DOM}createdAt"  # 대시보드 recent 용 생성 시각(런타임 저장분만)


def utc_now_iso() -> str:
    """대시보드 recent 의 `at` 값. 초 단위 ISO-8601 UTC."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

_SEED_GRAPH = "http://ex.org/seed/"  # 시드 파일별 그래프 prefix
_SCODE = re.compile(r"^S(\d+)$")


def _localname(iri: str) -> str:
    """IRI 의 로컬네임(마지막 # 또는 / 뒤)."""
    if "#" in iri:
        return iri.rsplit("#", 1)[1]
    return iri.rsplit("/", 1)[-1]


def _term_value(term: object) -> str:
    """pyoxigraph term → 파이썬(JSON 직렬화 가능) 값. NamedNode→IRI, Literal→lexical, Blank→_:id."""
    if isinstance(term, ox.NamedNode):
        return term.value
    if isinstance(term, ox.BlankNode):
        return f"_:{term.value}"
    if isinstance(term, ox.Literal):
        return term.value
    return str(term)


def _to_rdflib_term(term: object):  # noqa: ANN201
    """pyoxigraph term → rdflib term (subgraph/to_rdflib 브리지)."""
    from rdflib import BNode, Literal, URIRef

    if isinstance(term, ox.NamedNode):
        return URIRef(term.value)
    if isinstance(term, ox.BlankNode):
        return BNode(term.value)
    if isinstance(term, ox.Literal):
        dt = term.datatype
        lang = term.language
        if lang:
            return Literal(term.value, lang=lang)
        if dt is not None:
            return Literal(term.value, datatype=URIRef(dt.value))
        return Literal(term.value)
    raise TypeError(f"지원하지 않는 term: {term!r}")


class OxigraphStore:
    """`core.protocols.Store` 구현. 임베디드 pyoxigraph 영속 스토어."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            self._store = ox.Store()  # in-memory (테스트/휘발용)
        else:
            p = Path(path)
            p.mkdir(parents=True, exist_ok=True)
            self._store = ox.Store(path=str(p))
        self._seed_graphs: set[str] = set()

    # ── 조회 ────────────────────────────────────────────────────────────
    def query(self, sparql: str, *, readonly: bool = True) -> list[dict]:
        """SPARQL 질의 → list[dict].

        readonly=True 면 update 절을 게이트로 거부한다(계약: /sparql 읽기 전용).
        실행 자체도 `store.query()`(읽기 전용 실행기)만 사용한다.
        """
        if readonly:
            _gate.assert_readonly(sparql)
        try:
            result = self._store.query(sparql, use_default_graph_as_union=True)
        except SyntaxError as exc:  # 잘못된 SPARQL 문법 → 입력 오류
            raise ValidationError(
                internal=f"invalid sparql: {exc}",
                user_message="SPARQL 문법이 올바르지 않습니다.",
            ) from exc

        if isinstance(result, ox.QueryBoolean):
            return [{"ask": bool(result)}]
        if isinstance(result, ox.QueryTriples):  # CONSTRUCT/DESCRIBE
            return [
                {
                    "subject": _term_value(t.subject),
                    "predicate": _term_value(t.predicate),
                    "object": _term_value(t.object),
                }
                for t in result
            ]
        # SELECT
        variables = [v.value for v in result.variables]
        rows: list[dict] = []
        for sol in result:
            row: dict[str, str] = {}
            for var in variables:
                term = sol[ox.Variable(var)]
                if term is not None:
                    row[var] = _term_value(term)
            rows.append(row)
        return rows

    # ── 저장 (트리플만; 벡터는 호출자 kg.py 가 조율) ─────────────────────
    def save_sentence(
        self,
        sentence_text: str,
        category: str,
        mentions: list[str],
        *,
        about_symptom: str | None = None,
        polarity: str = "cause",
        code: str | None = None,
        draft_id: str | None = None,
    ) -> SavedSentence:
        """지식 문장 트리플을 default graph 에 커밋하고 SavedSentence 를 반환한다.

        `code` 미지정 시 기존 S1..Sn 최대값+1 로 발급(S7, S8 …).
        `draft_id` 지정 시 `dom:draftId` 로 심어 **영속 멱등 키**로 쓴다(T-83).
        """
        code = code or self.next_sentence_code()
        iri = f"{DOM}{code}"
        node = ox.NamedNode(iri)
        quads = [
            ox.Quad(node, ox.NamedNode(RDF_TYPE), ox.NamedNode(f"{DOM}KnowledgeSentence")),
            ox.Quad(node, ox.NamedNode(f"{DOM}sentenceText"), ox.Literal(sentence_text)),
            ox.Quad(node, ox.NamedNode(f"{DOM}category"), ox.Literal(category)),
            ox.Quad(node, ox.NamedNode(f"{DOM}polarity"), ox.Literal(polarity)),
            ox.Quad(node, ox.NamedNode(f"{DOM}basis"), ox.Literal(code)),
            ox.Quad(
                node,
                ox.NamedNode(CREATED_AT),
                ox.Literal(utc_now_iso(), datatype=ox.NamedNode(XSD_DATETIME)),
            ),
        ]
        if about_symptom:
            quads.append(
                ox.Quad(node, ox.NamedNode(f"{DOM}aboutSymptom"), ox.NamedNode(f"{DOM}{about_symptom}"))
            )
        for m in mentions:
            quads.append(ox.Quad(node, ox.NamedNode(f"{DOM}mentions"), ox.NamedNode(f"{DOM}{m}")))
        if draft_id:
            quads.append(ox.Quad(node, ox.NamedNode(f"{DOM}draftId"), ox.Literal(draft_id)))
        self._store.extend(quads)
        return SavedSentence(
            id=code,
            iri=iri,
            text=sentence_text,
            category=category,
            mentions=list(mentions),
            about_symptom=about_symptom,
            polarity=polarity,  # type: ignore[arg-type]
        )

    def sentence_by_draft_id(self, draft_id: str) -> SavedSentence | None:
        """T-83 — draft_id 로 이미 저장된 문장을 찾는다(영속 멱등). 없으면 None."""
        esc = draft_id.replace("\\", "\\\\").replace('"', '\\"')
        rows = self.query(
            f'SELECT ?s WHERE {{ ?s <{DOM}draftId> "{esc}" }}', readonly=False
        )
        return self._load_sentence(rows[0]["s"]) if rows else None

    def _load_sentence(self, iri: str) -> SavedSentence | None:
        def one(pred: str) -> str | None:
            r = self.query(f"SELECT ?o WHERE {{ <{iri}> <{pred}> ?o }}", readonly=False)
            return r[0]["o"] if r else None

        text = one(f"{DOM}sentenceText")
        if text is None:
            return None
        about = one(f"{DOM}aboutSymptom")
        ments = [
            _localname(r["o"])
            for r in self.query(f"SELECT ?o WHERE {{ <{iri}> <{DOM}mentions> ?o }}", readonly=False)
        ]
        return SavedSentence(
            id=_localname(iri),
            iri=iri,
            text=text,
            category=one(f"{DOM}category") or "",
            mentions=ments,
            about_symptom=_localname(about) if about else None,
            polarity=(one(f"{DOM}polarity") or "cause"),  # type: ignore[arg-type]
        )

    def next_sentence_code(self) -> str:
        """기존 KnowledgeSentence 의 S<n> 로컬네임 최대값 + 1."""
        rows = self.query(
            f"SELECT ?s WHERE {{ ?s a <{DOM}KnowledgeSentence> }}", readonly=False
        )
        mx = 0
        for r in rows:
            m = _SCODE.match(_localname(r["s"]))
            if m:
                mx = max(mx, int(m.group(1)))
        return f"S{mx + 1}"

    # ── 삭제 ────────────────────────────────────────────────────────────
    def remove_about(self, iri: str) -> list:
        """IRI 가 주어(또는 목적어)인 모든 quad 를 제거하고, 제거된 quad 목록을 반환한다.

        반환값을 `restore()` 에 넘기면 원상복구된다(kg.py 의 삭제 보상 롤백에 사용).
        """
        node = ox.NamedNode(iri)
        removed: list = []
        for q in list(self._store.quads_for_pattern(node, None, None, None)):
            removed.append(q)
        for q in list(self._store.quads_for_pattern(None, None, node, None)):
            removed.append(q)
        for q in removed:
            self._store.remove(q)
        return removed

    def restore(self, quads: list) -> None:
        """remove_about 이 돌려준 quad 들을 원래 그래프에 되돌린다."""
        if quads:
            self._store.extend(quads)

    def delete(self, iri: str) -> None:
        """IRI 주변 트리플 제거(Store Protocol). 반환 없음."""
        self.remove_about(iri)

    # ── reasoner(04) 입력용 부분그래프 ──────────────────────────────────
    def subgraph(self, iris: list[str], depth: int = 2) -> "Graph":
        """지정 IRI 에서 depth 홉 이내 트리플을 rdflib Graph 로 반환한다.

        각 홉마다 프런티어 노드의 **나가는/들어오는** 트리플을 모으고,
        새로 등장한 NamedNode/BlankNode 를 다음 프런티어로 확장한다.
        """
        from rdflib import Graph

        g = Graph()
        seen_quads: set = set()
        frontier = {i for i in iris}
        visited: set[str] = set()

        for _ in range(max(0, depth)):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for iri in frontier:
                if iri in visited:
                    continue
                visited.add(iri)
                node = ox.NamedNode(iri)
                quads = list(self._store.quads_for_pattern(node, None, None, None))
                quads += list(self._store.quads_for_pattern(None, None, node, None))
                for q in quads:
                    key = (q.subject, q.predicate, q.object)
                    if key in seen_quads:
                        continue
                    seen_quads.add(key)
                    g.add(
                        (
                            _to_rdflib_term(q.subject),
                            _to_rdflib_term(q.predicate),
                            _to_rdflib_term(q.object),
                        )
                    )
                    for term in (q.subject, q.object):
                        if isinstance(term, ox.NamedNode) and term.value not in visited:
                            next_frontier.add(term.value)
            frontier = next_frontier
        return g

    def to_rdflib(self) -> "Graph":
        """스토어 전체(모든 그래프)를 rdflib Graph 로 병합 반환."""
        from rdflib import Graph

        g = Graph()
        for q in self._store.quads_for_pattern(None, None, None, None):
            g.add(
                (
                    _to_rdflib_term(q.subject),
                    _to_rdflib_term(q.predicate),
                    _to_rdflib_term(q.object),
                )
            )
        return g

    # ── 시드 적재(멱등) ─────────────────────────────────────────────────
    def load_seed(self, ttl_paths: list) -> int:
        """m0/m1/rules/shapes 등 TTL 을 파일별 named graph 에 적재. 멱등.

        같은 파일을 다시 적재하면 해당 그래프를 CLEAR 후 다시 읽으므로 트리플 수가 늘지 않는다.
        반환값은 시드 그래프들에 적재된 총 트리플 수.
        """
        total = 0
        for path in ttl_paths:
            p = Path(path)
            gname = f"{_SEED_GRAPH}{p.stem}"
            self._seed_graphs.add(gname)
            # 재적재 대비: 기존 그래프 내용 제거(없어도 SILENT 로 무시)
            self._store.update(f"CLEAR SILENT GRAPH <{gname}>")
            self._store.load(
                path=str(p), format=ox.RdfFormat.TURTLE, to_graph=ox.NamedNode(gname)
            )
        for gname in self._seed_graphs:
            total += sum(
                1
                for _ in self._store.quads_for_pattern(None, None, None, ox.NamedNode(gname))
            )
        return total

    # ── 유틸 ────────────────────────────────────────────────────────────
    def triple_count(self) -> int:
        """스토어 전체 quad 수(테스트·헬스체크용)."""
        return len(self._store)

    def flush(self) -> None:
        self._store.flush()


# 왜 oxrdflib 를 쓰지 않았나:
#   oxrdflib 는 "pyoxigraph 를 rdflib 의 Store 백엔드로" 쓰는 어댑터다. 여기서 필요한 건
#   reasoner 에 넘길 **부분그래프 스냅샷**뿐이므로, 영속 스토어를 rdflib 추상화로 한 번 더
#   감싸는 대신 term 단위로 직접 변환한다. 이러면 스냅샷 안에서 블랭크노드 식별자가 안정적이고
#   의존 표면이 작다. 전체 그래프가 필요하면 to_rdflib() 를 쓴다.
