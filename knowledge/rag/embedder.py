"""임베딩 — 다국어 sentence-transformers, MOCK 우선(해시 결정론 벡터).

`interface_contracts.md` §2 `Embedder` Protocol 구현.
- `EMBEDDING_PROVIDER=mock`(기본): 패키지·모델 없이 결정론 벡터. 같은 입력 → 같은 벡터.
- `EMBEDDING_PROVIDER=local`: sentence-transformers. **lazy import**(함수 안에서만) — 모듈 최상단 import 금지.
- `local` 인데 패키지가 없으면 경고 로그 + mock 폴백(죽지 않는다).
- `EMBEDDING_PROVIDER=solar`: 미구현 — 경고 로그 + mock 폴백.
"""
from __future__ import annotations

import hashlib
import logging

from core.config import settings

log = logging.getLogger("rag.embedder")


class MockEmbedder:
    """결정론적 해시 임베딩(feature hashing) — 키·모델 없이 전 흐름 검증(MOCK 우선).

    문자 n-그램을 해시(the hashing trick)로 DIM 차원에 투영한 뒤 정규화한다.
    - 같은 텍스트 → 항상 같은 단위벡터(재현성).
    - 어휘가 겹치면 코사인 유사도가 올라간다 → "겨울/고무" 같은 표층 겹침 검색이 동작한다.
    의미(동의어·문맥)는 못 잡으므로 실제 검색 품질은 ST 임베딩보다 낮다(한계는 보고 참조).
    """

    # 가드: 컬렉션 차원과 어긋나지 않도록 설정 차원을 단일 진실원으로 쓴다(과거 256≠384 잠복 불일치).
    DIM = settings.embed_dim
    NGRAMS = (2, 3)  # 문자 bi/tri-그램
    ROOT_WEIGHT = 4  # 어근(토큰 앞 2글자) 가중 — 한국어 조사 변형 흡수
    name = "mock"

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _features(self, text: str):
        toks = text.split()
        feats: list[str] = []
        for t in toks:
            feats.append(t)  # 전체 토큰
            if len(t) >= 2:
                # 어근(앞 2글자)을 가중 반복 — "고무는/고무" 처럼 조사만 다른 매칭 강화
                feats.extend(["\x00R" + t[:2]] * self.ROOT_WEIGHT)
        s = "".join(toks)  # 공백 제거 문자열에서 문자 n-그램
        for n in self.NGRAMS:
            for i in range(len(s) - n + 1):
                feats.append(s[i : i + n])
        return feats

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        for feat in self._features(text):
            h = hashlib.sha256(feat.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "big") % self.DIM
            sign = 1.0 if (h[4] & 1) else -1.0  # 부호 해시로 충돌 상쇄
            vec[idx] += sign
        norm = sum(v * v for v in vec) ** 0.5
        if norm == 0.0:
            # 특성이 전혀 없을 때(빈 문자열 등)의 결정론 폴백
            b = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [(b[i % len(b)] / 255.0) * 2.0 - 1.0 for i in range(self.DIM)]
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]


class StEmbedder:
    """다국어 sentence-transformers 임베더. 모델은 `settings.local_embed_model`.

    sentence_transformers 는 **lazy import** — 인스턴스 생성 시점에만 로드한다.
    """

    def __init__(self, model_name: str | None = None) -> None:
        from sentence_transformers import SentenceTransformer  # lazy import (필수)

        self.model_name = model_name or settings.local_embed_model
        self._model = SentenceTransformer(self.model_name)

    @property
    def name(self) -> str:
        return self.model_name

    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return [v.tolist() for v in vecs]


def get_embedder(mode: str | None = None) -> MockEmbedder | StEmbedder:
    """`settings.embedding_provider` 로 임베더 선택.

    `local` 인데 sentence-transformers 가 없으면 경고 후 MockEmbedder 로 폴백한다(서비스 지속).
    `solar` 는 미구현 — 경고 후 mock 폴백. `st` 는 구표기 호환으로 `local` 과 같게 받는다.
    """
    mode = (mode or settings.embedding_provider or "mock").lower()
    if mode in ("local", "st"):  # "st" 는 구표기 호환
        try:
            return StEmbedder()
        except Exception as exc:  # noqa: BLE001 — 패키지 부재·모델 로드 실패 모두 폴백
            log.warning(
                "EMBEDDING_PROVIDER=local 이나 sentence-transformers 사용 불가(%s) — mock 임베딩으로 폴백",
                type(exc).__name__,
            )
            return MockEmbedder()
    if mode == "solar":
        log.warning("EMBEDDING_PROVIDER=solar 는 미구현 — mock 임베딩으로 폴백")
        return MockEmbedder()
    return MockEmbedder()


def embedder_signature(embedder: MockEmbedder | StEmbedder) -> tuple[str, int]:
    """(모델명, 차원) — Chroma 컬렉션 메타에 실어 임베더 교체를 구조적으로 감지한다(가드).

    차원은 실제 인코딩 결과로 확정한다(모델이 표방한 값과 어긋나지 않게).
    """
    vec = embedder.encode(["차원 프로브"])[0]
    return getattr(embedder, "name", type(embedder).__name__), len(vec)
