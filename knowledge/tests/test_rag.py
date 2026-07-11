"""03 RAG 레이어 테스트 — mock 우선, Chroma 임베디드.

실행: knowledge/ 에서
    .venv/Scripts/python.exe -m pytest tests/test_rag.py -q
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from rag.embedder import MockEmbedder, get_embedder
from rag.retriever import ChromaRetriever, MockProjectScopeProvider
from rag.sources import TtlSentenceSource
from rag.verifier import MockRuleVerifier
from schemas.errors import AppError
from schemas.models import RagSearchResponse


# ── 픽스처 ───────────────────────────────────────────────────────────────────
@pytest.fixture()
def source() -> TtlSentenceSource:
    return TtlSentenceSource()


@pytest.fixture()
def retriever(tmp_path, source) -> ChromaRetriever:
    """테스트마다 격리된 Chroma 경로 사용."""
    return ChromaRetriever(
        embedder=MockEmbedder(),
        source=source,
        verifier=MockRuleVerifier(source.known_rules()),
        scope_provider=MockProjectScopeProvider(),
        chroma_path=tmp_path / "chroma",
        collection_name="test_sentences",
    )


# ── 1. mock 임베딩 결정론 ────────────────────────────────────────────────────
def test_mock_embedding_deterministic():
    emb = MockEmbedder()
    a = emb.encode(["겨울에 고무 블레이드를 쓰면?"])[0]
    b = emb.encode(["겨울에 고무 블레이드를 쓰면?"])[0]
    assert a == b
    # 정규화 단위벡터
    norm = sum(v * v for v in a) ** 0.5
    assert abs(norm - 1.0) < 1e-9
    # 다른 입력은 다른 벡터
    c = emb.encode(["실리콘은 소음을 해소한다"])[0]
    assert a != c


# ── 2. ensure_indexed 멱등 + 6문장 ──────────────────────────────────────────
def test_ensure_indexed_idempotent(retriever):
    n1 = retriever.ensure_indexed()
    n2 = retriever.ensure_indexed()
    assert n1 == n2 == 6  # m1_wiper 의 S1~S6
    assert retriever.count() == 6


def test_mock_dim_follows_settings():
    """가드: MockEmbedder.DIM 은 settings.embed_dim 을 따른다(과거 256≠384 잠복 불일치 차단)."""
    from core.config import settings

    assert MockEmbedder.DIM == settings.embed_dim
    assert len(MockEmbedder().encode(["x"])[0]) == settings.embed_dim


def test_collection_embedder_mismatch_drops_and_recreates(tmp_path, source):
    """가드: 컬렉션 메타(embedder_model·embed_dim)가 임베더와 어긋나면 drop→recreate 한다.

    provider 전환 후 'data/chroma 삭제 깜빡' → 차원 불일치·엉뚱한 유사도(무증상)를 구조적으로 막는다.
    """
    path = tmp_path / "chroma"
    r1 = ChromaRetriever(
        embedder=MockEmbedder(), source=source,
        verifier=MockRuleVerifier(source.known_rules()),
        scope_provider=MockProjectScopeProvider(),
        chroma_path=path, collection_name="guard_sentences",
    )
    assert r1.ensure_indexed() == 6
    assert r1._col.metadata["embed_dim"] == MockEmbedder.DIM

    class TinyMock(MockEmbedder):  # 차원이 다른 임베더로 교체된 상황
        DIM = 8
        name = "mock"

    r2 = ChromaRetriever(
        embedder=TinyMock(), source=source,
        verifier=MockRuleVerifier(source.known_rules()),
        scope_provider=MockProjectScopeProvider(),
        chroma_path=path, collection_name="guard_sentences",
    )
    # 불일치 감지 → 컬렉션이 비워졌다(재인덱싱 전 count 0), 메타는 새 차원.
    assert r2._col.count() == 0
    assert r2._col.metadata["embed_dim"] == 8
    assert r2.ensure_indexed() == 6  # 새 공간에 재인덱싱


# ── 3. 겨울/고무 검색 → S1 상위 + sufficient ─────────────────────────────────
def test_search_winter_rubber_s1_top(retriever):
    retriever.ensure_indexed()
    hits = retriever.search("겨울에 고무 블레이드를 쓰면?", k=6, project_id="proj-winter-suv")
    assert hits, "검색 결과가 비어 있으면 안 된다"
    codes = [h.sentence for h in hits]
    assert "S1" in codes
    # S1 이 상위(첫 결과)
    assert hits[0].sentence == "S1"
    assert hits[0].derives_rule == "NoiseRule"
    assert hits[0].verified is True
    assert retriever.is_sufficient(hits) is True


# ── 4. 음성 테스트: 모든 hit verified=False → sufficient=False ───────────────
def test_all_unverified_not_sufficient(tmp_path, source):
    class _AlwaysFalse:
        def is_verified(self, rule_id, categories):  # noqa: ANN001
            return False

    r = ChromaRetriever(
        embedder=MockEmbedder(),
        source=source,
        verifier=_AlwaysFalse(),
        scope_provider=MockProjectScopeProvider(),
        chroma_path=tmp_path / "chroma",
        collection_name="test_unverified",
    )
    r.ensure_indexed()
    hits = r.search("겨울에 고무 블레이드를 쓰면?", k=6)
    assert hits
    assert all(h.verified is False for h in hits)
    assert r.is_sufficient(hits) is False  # 미검증 근거 0 보장


# ── 5. 계약 스키마 준수 (라우터 경유) ────────────────────────────────────────
def test_contract_schema_via_route(tmp_path, source):
    from rag import routes as rag_routes

    r = ChromaRetriever(
        embedder=MockEmbedder(),
        source=source,
        verifier=MockRuleVerifier(source.known_rules()),
        scope_provider=MockProjectScopeProvider(),
        chroma_path=tmp_path / "chroma",
        collection_name="test_route",
    )
    r.ensure_indexed()

    app = FastAPI()
    app.include_router(rag_routes.router)
    app.dependency_overrides[rag_routes.get_retriever] = lambda: r

    @app.exception_handler(AppError)
    async def _h(request, exc):  # noqa: ANN001
        return JSONResponse(status_code=exc.http_status, content=exc.to_body("t"))

    client = TestClient(app)
    resp = client.post(
        "/rag/search",
        json={"query": "겨울에 고무 블레이드를 쓰면?", "k": 6, "project_id": "proj-winter-suv"},
    )
    assert resp.status_code == 200, resp.text
    parsed = RagSearchResponse.model_validate(resp.json())  # 계약 스키마 준수
    assert parsed.sufficient is True
    assert any(h.sentence == "S1" for h in parsed.hits)

    # /categories 계약 형태
    cat = client.get("/categories")
    assert cat.status_code == 200
    names = {c["name"]: c for c in cat.json()["categories"]}
    assert names["소음"]["sentences"] == 2 and names["소음"]["rules"] == 2
    assert names["떨림"]["sentences"] == 4 and names["떨림"]["rules"] == 3


# ── 6. EMBEDDING_PROVIDER=local 인데 패키지 없음 → mock 폴백(예외 없음) ───────
# 기본 CI 는 requirements.txt 만 설치한다(ML 미포함) — requirements-ml.txt 를 넣으면
# 이 테스트가 StEmbedder 를 받아 실패한다. 실제 ST 검증은 ML 설치 잡에서 별도로.
def test_st_mode_falls_back_to_mock():
    emb = get_embedder(mode="local")
    # sentence-transformers 미설치 환경에서는 MockEmbedder 로 폴백
    assert isinstance(emb, MockEmbedder)
    vec = emb.encode(["폴백 확인"])[0]
    assert len(vec) == MockEmbedder.DIM


# ── 보너스: routes 모듈 import 부작용 없음(최상단 Chroma 미개방) ─────────────
def test_routes_import_no_side_effect():
    import importlib

    import rag.routes as rr

    importlib.reload(rr)
    assert rr._retriever is None
