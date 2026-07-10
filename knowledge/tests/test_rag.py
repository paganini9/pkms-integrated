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


# ── 6. EMBEDDING_MODE=st 인데 패키지 없음 → mock 폴백(예외 없음) ─────────────
def test_st_mode_falls_back_to_mock():
    emb = get_embedder(mode="st")
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
