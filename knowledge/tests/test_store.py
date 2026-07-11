"""06 퍼시스턴스 레이어 테스트 — Oxigraph 임베디드, 벡터 원자성, 읽기전용 게이트.

실행: knowledge/ 에서
    .venv/Scripts/python.exe -m pytest tests/test_store.py -q

모든 스토어는 tmp_path 로 격리한다(사용자 data/ 오염 금지).
"""
from __future__ import annotations

import pytest

from core.config import settings
from schemas.errors import StoreError, ValidationError
from schemas.models import SaveRequest, SaveResponse
from store.kg import KgService
from store.oxigraph import DOM, OxigraphStore
from store.projects import ProjectService
from store.sparql import assert_readonly, is_readonly


# ── 픽스처 ───────────────────────────────────────────────────────────────────
def _seed_paths() -> list:
    return [p for p in settings.seed_ttl if p.exists()]


@pytest.fixture()
def store(tmp_path) -> OxigraphStore:
    s = OxigraphStore(tmp_path / "oxigraph")
    s.load_seed(_seed_paths())
    return s


# ── 스파이 Retriever ─────────────────────────────────────────────────────────
class SpyRetriever:
    """upsert/delete 호출을 기록한다."""

    def __init__(self) -> None:
        self.upserts: list = []
        self.deletes: list = []

    def upsert(self, items):  # noqa: ANN001
        self.upserts.append(items)
        return len(items)

    def delete(self, iris):  # noqa: ANN001
        self.deletes.append(iris)
        return len(iris)


class FailingRetriever(SpyRetriever):
    """벡터 upsert 가 항상 실패 → 원자성(롤백) 검증용."""

    def upsert(self, items):  # noqa: ANN001
        raise RuntimeError("주입된 벡터 upsert 실패")


def _save_request() -> SaveRequest:
    return SaveRequest(
        sentence_text="겨울철 저온에서 고무는 경도가 상승해 소음을 유발한다.",
        concepts=[
            {"label": "겨울철", "type": "EnvCondition"},
            {"label": "고무", "type": "Material"},
            {"label": "소음", "type": "Symptom"},
        ],
        relations=[{"subject": "고무", "predicate": "causes", "object": "소음", "evidence": "S1"}],
        category="소음",
        approved=True,
    )


# ── 1. load_seed 멱등 ────────────────────────────────────────────────────────
def test_load_seed_idempotent(tmp_path):
    s = OxigraphStore(tmp_path / "ox")
    n1 = s.load_seed(_seed_paths())
    total1 = s.triple_count()
    n2 = s.load_seed(_seed_paths())  # 두 번째 적재
    total2 = s.triple_count()
    assert n1 == n2, "적재 트리플 수가 재적재 후 달라짐"
    assert total1 == total2, "재적재로 스토어 트리플 수가 증가함(블랭크노드 중복)"
    assert n1 > 0


# ── 2. 읽기 전용 게이트 ──────────────────────────────────────────────────────
def test_readonly_allows_read_forms():
    for q in [
        "SELECT ?s WHERE { ?s ?p ?o }",
        "PREFIX dom: <http://ex.org/domain#> SELECT ?s WHERE { ?s a dom:WiperBlade }",
        "ASK { ?s ?p ?o }",
        "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
        "DESCRIBE <http://ex.org/domain#S1>",
    ]:
        assert is_readonly(q)
        assert_readonly(q)  # 예외 없음


def test_readonly_rejects_updates():
    for q in [
        'INSERT DATA { <http://a> <http://p> "x" }',
        "DELETE WHERE { ?s ?p ?o }",
        "LOAD <http://ex.org/data.ttl>",
        "CLEAR GRAPH <http://ex.org/g>",
        "DROP GRAPH <http://ex.org/g>",
        "WITH <http://ex.org/g> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
    ]:
        assert not is_readonly(q)
        with pytest.raises(ValidationError):
            assert_readonly(q)


def test_readonly_not_fooled_by_comments_or_literals():
    # 주석 속 DELETE 는 통과
    q1 = "# DELETE everything now\nSELECT ?s WHERE { ?s ?p ?o }"
    # 리터럴 속 INSERT DATA 는 통과
    q2 = 'SELECT ?s WHERE { ?s ?p "INSERT DATA" }'
    # IRI 안의 DROP 도 통과
    q3 = "SELECT ?s WHERE { ?s ?p <http://ex.org/DROP#x> }"
    for q in (q1, q2, q3):
        assert is_readonly(q), q
        assert_readonly(q)


def test_readonly_gate_enforced_via_store_query(store):
    with pytest.raises(ValidationError):
        store.query('INSERT DATA { <http://a> <http://p> "x" }')  # readonly=True 기본


# ── 3. /kg/save 성공 → 트리플 증가 + 벡터 upsert + SaveResponse 검증 ─────────
def test_kg_save_success(store):
    spy = SpyRetriever()
    kg = KgService(store, retriever=spy)
    before = store.triple_count()

    resp = kg.save(_save_request())

    assert store.triple_count() > before, "트리플이 늘지 않음"
    assert len(spy.upserts) == 1, "벡터 upsert 가 호출되지 않음"
    # SaveResponse 스키마 검증(계약 형태)
    SaveResponse.model_validate(resp.model_dump())
    # 신규 코드는 시드(S1..S6) 다음 → S7
    assert resp.sentence.id == "S7"
    assert resp.sentence.iri == f"{DOM}S7"
    # best-effort 라벨 해석: 겨울철→Winter, 고무→Rubber, 소음→Noise
    assert resp.sentence.mentions == ["Winter", "Rubber", "Noise"]
    assert resp.sentence.about_symptom == "Noise"
    assert resp.sentence.polarity == "cause"
    # rules.ttl 폴백으로 NoiseRule 파생
    assert resp.derived.rule.id == "NoiseRule"
    assert resp.derived.shapes[0].id == "NoiseShape"


def test_kg_save_idempotent_by_draft_id(store):
    """T-83 — 같은 draft_id 재전송은 중복 저장 0. **BFF 재기동(새 서비스 인스턴스)에도** 멱등.

    과거 멱등은 BFF in-memory Map 이라 재기동 시 소실됐다. 이제 draft_id 가 트리플에 남아 영속.
    """
    kg1 = KgService(store, retriever=SpyRetriever())
    r1 = kg1.save(_save_request().model_copy(update={"draft_id": "draft-xyz"}))
    triples_after_first = store.triple_count()

    # 재기동 흉내: 새 KgService·새 retriever, 같은 store·같은 draft_id 재전송.
    spy2 = SpyRetriever()
    kg2 = KgService(store, retriever=spy2)
    r2 = kg2.save(_save_request().model_copy(update={"draft_id": "draft-xyz"}))

    assert r2.sentence.iri == r1.sentence.iri, "멱등인데 다른 문장이 생겼다"
    assert store.triple_count() == triples_after_first, "중복 저장으로 트리플이 늘었다"
    assert len(spy2.upserts) == 0, "멱등 재전송인데 벡터를 다시 upsert 했다"


# ── 4. 원자성: 벡터 실패 → StoreError + 트리플 원상복구 ─────────────────────
def test_kg_save_atomic_rollback(store):
    kg = KgService(store, retriever=FailingRetriever())
    before = store.triple_count()

    with pytest.raises(StoreError):
        kg.save(_save_request())

    assert store.triple_count() == before, "벡터 실패 후 트리플이 원상복구되지 않음"
    # 롤백되었으므로 다음 코드는 여전히 S7
    assert store.next_sentence_code() == "S7"


def test_kg_delete_atomic_rollback(store):
    # 먼저 정상 저장
    spy = SpyRetriever()
    kg = KgService(store, retriever=spy)
    resp = kg.save(_save_request())
    after_save = store.triple_count()

    # 삭제 시 벡터가 실패하도록 주입
    class DelFail(SpyRetriever):
        def delete(self, iris):  # noqa: ANN001
            raise RuntimeError("주입된 벡터 삭제 실패")

    kg.retriever = DelFail()
    with pytest.raises(StoreError):
        kg.delete([resp.sentence.iri])
    assert store.triple_count() == after_save, "삭제 실패 후 트리플이 복구되지 않음"


# ── 5. 지식범위 게이트 수 ────────────────────────────────────────────────────
def test_knowledge_scope_gate_counts(store):
    proj = ProjectService(store)
    p = proj.create("겨울용 SUV", "MidSizeSUV", ["소음", "떨림"], target_env="Winter")

    r_both = proj.set_knowledge_scope(p["id"], ["소음", "떨림"])
    assert r_both.compiled_gates == 4, "{소음,떨림} 게이트는 4개여야 함"

    r_chatter = proj.set_knowledge_scope(p["id"], ["떨림"])
    assert r_chatter.compiled_gates == 3, "{떨림} 게이트는 3개여야 함(mitigate 제외)"


def test_project_crud_roundtrip(store):
    proj = ProjectService(store)
    p = proj.create("겨울용 SUV", "MidSizeSUV", ["소음", "떨림"], target_env="Winter")
    got = proj.get(p["id"])
    assert got["name"] == "겨울용 SUV"
    assert got["target_vehicle"] == "MidSizeSUV"
    assert got["target_env"] == "Winter"
    assert set(got["knowledge_categories"]) == {"소음", "떨림"}

    out = proj.add_requirements(
        p["id"],
        [
            {"id": "RB_Winter", "label": "겨울 저소음(소음 없음)", "forbids_symptom": "Noise"},
            {"id": "RB_NoChatter", "label": "끝단 떨림 없음", "forbids_symptom": "TipChatter"},
        ],
    )
    ids = {r["id"] for r in out["requirements"]}
    assert ids == {"RB_Winter", "RB_NoChatter"}


# ── 6. subgraph 는 rdflib Graph 이고 지정 IRI 주변 트리플을 포함 ─────────────
def test_subgraph_returns_rdflib_graph(store):
    from rdflib import Graph, URIRef

    g = store.subgraph([f"{DOM}S1"], depth=2)
    assert isinstance(g, Graph)
    assert len(g) > 0
    s1 = URIRef(f"{DOM}S1")
    # S1 이 주어인 트리플이 하나 이상 포함
    assert any(s == s1 for s, _p, _o in g), "지정 IRI 주변 트리플이 없음"
    # depth 2 확장으로 S1 이 언급한 Winter 노드도 그래프에 등장
    subjects_objects = {str(t) for triple in g for t in triple}
    assert f"{DOM}Winter" in subjects_objects
