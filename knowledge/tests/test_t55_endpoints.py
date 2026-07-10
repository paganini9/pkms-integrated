"""T-55 (Phase 2) — CD-10·CD-11 신설 엔드포인트 테스트.

- HTTP 레벨: 실제 앱(main.app)을 TestClient 로 두드린다(영속 스토어 사용, 쓰기 없는 케이스만).
- 유닛 레벨: tmp_path 스토어로 격리해 상태 변경(거버넌스 생성·삭제·프로젝트 M2)을 검증한다.

**음성 테스트(negative)** 를 반드시 포함한다 — 검증기가 no-op 이 아님을 보인다:
  · 화이트리스트 밖 질의 → 422
  · SPARQL 주입 시도(initBindings 로 무해) → 200 빈 결과 (질의 구조 안 바뀜)
  · builtin 개념 삭제 → 400 BUILTIN_LOCKED
  · 미승인 저장(approved:false) → 409 GUARDRAIL_BLOCKED
"""
from __future__ import annotations

import gc

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from schemas.models import GraphResponse, LookupResponse
from store.governance import GovernanceService
from store.graph import GraphBuilder
from store.lookup import KgLookup
from store.oxigraph import OxigraphStore
from store.projects import ProjectService


def _seed_paths() -> list:
    return [p for p in settings.seed_ttl if p.exists()]


@pytest.fixture()
def store(tmp_path) -> OxigraphStore:
    s = OxigraphStore(tmp_path / "oxigraph")
    s.load_seed(_seed_paths())
    return s


@pytest.fixture(scope="module")
def client() -> TestClient:
    import main

    with TestClient(main.app) as c:
        yield c


# ════════════════════════ CD-11 · POST /kg/lookup ════════════════════════
def test_lookup_max_safe_length(client: TestClient) -> None:
    r = client.post("/kg/lookup", json={"query": "max_safe_length", "params": {"vehicle": "MidSizeSUV"}})
    assert r.status_code == 200
    body = r.json()
    LookupResponse.model_validate(body)
    assert {"vehicle": "MidSizeSUV", "max_safe_mm": 599, "sentence": "S3"} in body["rows"]
    assert any(s["sentence"] == "S3" for s in body["sources"])
    assert body["sources"][0]["text"]  # 근거 문장 텍스트가 실린다


def test_lookup_symptom_causes(client: TestClient) -> None:
    r = client.post("/kg/lookup", json={"query": "symptom_causes", "params": {"symptom": "TipChatter"}})
    assert r.status_code == 200
    rules = {row["rule"] for row in r.json()["rows"]}
    assert rules == {"ChatterRule", "SpringRule", "ArmRule"}  # mitigate 제외


def test_lookup_rule_sentences(client: TestClient) -> None:
    r = client.post("/kg/lookup", json={"query": "rule_sentences", "params": {"rule": "ChatterRule"}})
    assert r.status_code == 200
    assert [row["sentence"] for row in r.json()["rows"]] == ["S3", "S5"]


def test_lookup_concept_relations(client: TestClient) -> None:
    r = client.post("/kg/lookup", json={"query": "concept_relations", "params": {"concept": "Rubber"}})
    assert r.status_code == 200
    assert {"subject": "Rubber", "predicate": "causes", "object": "Noise"} in r.json()["rows"]


def test_lookup_empty_rows_is_not_error(client: TestClient) -> None:
    """rows 가 비어도 예외가 아니라 200 빈 배열 (BFF 가 '근거 없음' 분기로 간다)."""
    r = client.post("/kg/lookup", json={"query": "rule_sentences", "params": {"rule": "존재하지않는규칙"}})
    assert r.status_code == 200
    assert r.json()["rows"] == []


# ── 음성: 화이트리스트 밖 ────────────────────────────────────────────────────
def test_lookup_rejects_query_outside_whitelist(client: TestClient) -> None:
    r = client.post("/kg/lookup", json={"query": "select_all_secrets", "params": {}})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "detail" not in body  # FastAPI 기본 형태가 새어 나오지 않는다


def test_lookup_missing_param_is_422(client: TestClient) -> None:
    r = client.post("/kg/lookup", json={"query": "max_safe_length", "params": {}})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


# ── 음성: SPARQL 주입 시도 → initBindings 로 무해 ────────────────────────────
def test_lookup_injection_attempt_is_harmless(client: TestClient) -> None:
    """params 값에 SPARQL 파편을 넣어도 질의 구조가 바뀌지 않는다(주입 차단).

    문자열 보간이면 이 값이 WHERE 절을 깨거나 DELETE 를 주입할 수 있다. initBindings 라 무해한
    (존재하지 않는) IRI 로 바인딩되어 빈 결과가 나올 뿐이다.
    """
    for payload in ('> ?x } DELETE { ?s ?p ?o } INSERT { ?s ?p "z"', "Rubber> ; ?p ?o . }"):
        r = client.post("/kg/lookup", json={"query": "max_safe_length", "params": {"vehicle": payload}})
        assert r.status_code == 200, payload
        assert r.json()["rows"] == [], f"주입 값이 결과를 만들어냈다: {payload}"


def test_lookup_injection_does_not_mutate_store(client: TestClient) -> None:
    """주입 시도가 스토어를 변형하지 않았는지 — 이후 정상 질의가 그대로 동작한다."""
    client.post("/kg/lookup", json={"query": "symptom_causes", "params": {"symptom": '"} DELETE { ?s ?p ?o'}})
    r = client.post("/kg/lookup", json={"query": "max_safe_length", "params": {"vehicle": "MidSizeSUV"}})
    assert r.json()["rows"] == [{"vehicle": "MidSizeSUV", "max_safe_mm": 599, "sentence": "S3"}]


# 유닛(격리 스토어)에서도 화이트리스트 게이트가 실제로 막는지 확인 — 검증기가 no-op 이 아님
def test_lookup_whitelist_enforced_at_service(store: OxigraphStore) -> None:
    from schemas.errors import ValidationError

    with pytest.raises(ValidationError):
        KgLookup(store).lookup("rm_rf", {})


# ════════════════════════ CD-10 · GET /graph ════════════════════════════
def test_graph_full_has_real_inferred_edge(client: TestClient) -> None:
    """inferred 는 실제 추론(이행 폐포)으로 생긴 엣지다 — 가짜가 아니다.

    시드의 has_subbehavior 는 owl:TransitiveProperty → WipingBehavior⇝ContactBehavior 가
    명시되지 않았지만 이행 폐포로 도출된다.
    """
    body = client.get("/graph").json()
    GraphResponse.model_validate(body)
    inferred = [e for e in body["edges"] if e["inferred"]]
    assert body["stats"]["inferred_edges"] == len(inferred)
    assert any(
        e["source"] == "WipingBehavior" and e["target"] == "ContactBehavior" for e in inferred
    ), "이행 폐포 추론 엣지가 없다"


def test_graph_limit_is_applied(client: TestClient) -> None:
    body = client.get("/graph", params={"limit": 3}).json()
    assert len(body["nodes"]) == 3
    assert body["stats"]["truncated"] is True
    # 절단 후 엣지는 남은 노드만 참조한다(고아 엣지 없음)
    ids = {n["id"] for n in body["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in body["edges"])


def test_graph_layer_filter(client: TestClient) -> None:
    body = client.get("/graph", params={"layer": "M0"}).json()
    assert body["nodes"], "M0 클래스 노드가 있어야 한다"
    assert all(n["layer"] == "M0" for n in body["nodes"])


def test_graph_is_deterministic(client: TestClient) -> None:
    a = client.get("/graph", params={"limit": 500}).json()
    b = client.get("/graph", params={"limit": 500}).json()
    assert a["nodes"] == b["nodes"]
    assert a["edges"] == b["edges"]


def test_graph_no_blanknodes_or_triples_leak(client: TestClient) -> None:
    """내부 구조 비노출 — 블랭크노드가 id/iri 로 새어 나오면 안 된다."""
    body = client.get("/graph").json()
    for n in body["nodes"]:
        assert not n["id"].startswith("_:")
        assert "://" in n["iri"] and "nodeID" not in n["iri"]


def test_graph_sentence_filter_neighborhood(store: OxigraphStore) -> None:
    g = GraphBuilder(store).build(sentence="S3")
    ids = {n.id for n in g.nodes}
    assert "S3" in ids
    assert "ChatterRule" in ids  # S3 → derivesRule ChatterRule (1홉)
    assert "TipChatter" in ids


def test_graph_project_appears_as_m2(store: OxigraphStore) -> None:
    proj = ProjectService(store)
    p = proj.create("겨울용 SUV", "MidSizeSUV", ["소음", "떨림"], target_env="Winter")
    g = GraphBuilder(store).build(layer="M2")
    kinds = {n.id: n.kind for n in g.nodes}
    proj_local = p["iri"].rsplit("#", 1)[-1]
    assert proj_local in kinds and kinds[proj_local] == "class"


# ════════════════════════ CD-10 · GET /dashboard ════════════════════════
def test_dashboard_shape_and_counts(client: TestClient) -> None:
    body = client.get("/dashboard").json()
    for key in ("m0", "m1", "m2", "recent", "trace_id"):
        assert key in body
    assert body["m1"]["sentences"] >= 6  # 시드 6문장 (+ 이전 실행 저장분 가능)
    assert body["m1"]["rules"] == 5
    assert set(body["m0"]) == {"classes", "relations"}
    assert set(body["m2"]) == {"projects", "designs", "violations"}
    assert isinstance(body["recent"], list)


def test_dashboard_recent_reflects_saved_project(store: OxigraphStore) -> None:
    from store.dashboard import DashboardService

    ProjectService(store).create("최근 프로젝트", "MidSizeSUV", ["떨림"])
    recent = DashboardService(store).summary()["recent"]
    assert any(item["kind"] == "project" and item["at"] for item in recent)


# ════════════════════════ CD-10 · /governance/concepts ══════════════════
def test_governance_lists_8_builtin(client: TestClient) -> None:
    body = client.get("/governance/concepts").json()
    ids = {c["id"] for c in body["builtin"]}
    assert ids == {
        "PartType", "Component", "Material", "VehicleType",
        "EnvCondition", "Symptom", "Behavior", "Attribute",
    }


# ── 음성: 미승인 저장 → 409 ──────────────────────────────────────────────────
def test_governance_unapproved_create_blocked(client: TestClient) -> None:
    r = client.post(
        "/governance/concepts", json={"id": "Vibration", "label": "진동", "parent": "Symptom", "approved": False}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "GUARDRAIL_BLOCKED"


# ── 음성: builtin 삭제 → 400 ─────────────────────────────────────────────────
def test_governance_builtin_delete_locked(client: TestClient) -> None:
    r = client.delete("/governance/concepts/Symptom")
    assert r.status_code == 400
    assert r.json()["code"] == "BUILTIN_LOCKED"


def test_governance_create_delete_roundtrip(store: OxigraphStore) -> None:
    gov = GovernanceService(store)
    gov.create("Vibration", "진동", "Symptom", approved=True)
    custom_ids = {c["id"] for c in gov.list()["custom"]}
    assert "Vibration" in custom_ids
    gov.delete("Vibration")
    assert "Vibration" not in {c["id"] for c in gov.list()["custom"]}


def test_governance_custom_persists_across_reopen(tmp_path) -> None:
    """custom 개념은 영속되어야 한다(재기동 후 유지) — Oxigraph 디스크 영속."""
    path = tmp_path / "gov_ox"
    s1 = OxigraphStore(path)
    s1.load_seed(_seed_paths())
    GovernanceService(s1).create("Vibration", "진동", "Symptom", approved=True)
    s1.flush()
    del s1
    gc.collect()

    s2 = OxigraphStore(path)  # 재기동 시뮬레이션
    assert "Vibration" in {c["id"] for c in GovernanceService(s2).list()["custom"]}


def test_governance_builtin_delete_locked_at_service(store: OxigraphStore) -> None:
    from schemas.errors import BuiltinLocked

    with pytest.raises(BuiltinLocked):
        GovernanceService(store).delete("Material")
