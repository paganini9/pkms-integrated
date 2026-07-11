"""G1 게이트 — 결선된 지식서비스가 계약과 회귀셋을 만족하는지 확인한다.

레이어 단위 테스트(test_rag·test_store·test_reasoning)와 달리, 여기서는 **실제 앱**을 띄우고
HTTP 표면으로 두드린다. mock↔실구현 교체가 끝났는지(G1 조건)가 여기서 드러난다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from schemas.models import RagSearchResponse, SatisfyResponse, ValidateResponse

BAD = {"material": "Rubber", "length_mm": 600, "spring_n": 8, "arm_shape": "simple", "vehicle": "MidSizeSUV", "env": "Winter"}
GOOD = {"material": "Silicone", "length_mm": 550, "spring_n": 12, "arm_shape": "complex", "vehicle": "CompactSedan", "env": "Winter"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    import main

    with TestClient(main.app) as c:
        yield c


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["reasoner"] in {"ok", "no_jre"}  # JRE 없으면 정직하게 no_jre


def test_trace_id_전파(client: TestClient) -> None:
    r = client.post("/satisfy", json={"design": BAD, "require": ["RB_Winter"]}, headers={"X-Trace-Id": "g1-trace"})
    assert r.json()["trace_id"] == "g1-trace"
    assert r.headers["X-Trace-Id"] == "g1-trace"


# ── 회귀셋 ────────────────────────────────────────────────────────────────
def test_회귀_sat_bad(client: TestClient) -> None:
    body = client.post(
        "/satisfy", json={"design": BAD, "require": ["RB_Winter", "RB_NoChatter"], "categories": ["소음", "떨림"]}
    ).json()
    SatisfyResponse.model_validate(body)
    assert body["satisfies"] is False
    assert body["violations"] == ["S1", "S3", "S4", "S6"]
    assert body["violation_bases"] == ["S1", "S3,S5", "S4", "S6"]


def test_satisfy_캐시가_HTTP_경로에서도_잡힌다(client: TestClient) -> None:
    """단위 테스트는 통과하는데 HTTP 에서 안 잡히던 버그 — pySHACL 의 shapes 오염이 원인이었다."""
    body = {"design": GOOD, "require": ["RB_Winter"], "categories": ["소음", "떨림"]}
    client.post("/satisfy", json=body)  # 워밍업
    assert client.post("/satisfy", json=body).json()["cache_hit"] is True


def test_rules_compile_은_호출해도_shapes가_부풀지_않는다(client: TestClient) -> None:
    first = client.post("/rules/compile", json={"categories": ["소음", "떨림"]}).json()["shapes_ttl"]
    client.post("/satisfy", json={"design": BAD, "require": ["RB_Winter"], "categories": ["소음", "떨림"]})
    second = client.post("/rules/compile", json={"categories": ["소음", "떨림"]}).json()["shapes_ttl"]
    assert len(first) == len(second), "satisfy 실행이 정본 shapes 를 오염시켰다"


def test_회귀_sat_good(client: TestClient) -> None:
    body = client.post(
        "/satisfy", json={"design": GOOD, "require": ["RB_Winter", "RB_NoChatter"], "categories": ["소음", "떨림"]}
    ).json()
    assert body["satisfies"] is True and body["violations"] == []


def test_회귀_scope_A_와_scope_B(client: TestClient) -> None:
    """AC-scope — 같은 설계, 다른 지식범위 → 다른 결과 (CD-4)."""
    a = client.post(
        "/satisfy", json={"design": BAD, "require": ["RB_Winter", "RB_NoChatter"], "categories": ["소음", "떨림"]}
    ).json()
    b = client.post("/satisfy", json={"design": BAD, "require": ["RB_NoChatter"], "categories": ["떨림"]}).json()
    assert a["violation_bases"] == ["S1", "S3,S5", "S4", "S6"]
    assert b["violation_bases"] == ["S3,S5", "S4", "S6"]


def test_회귀_sat_pending(client: TestClient) -> None:
    """CD-8 — spring_n 결측은 422 가 아니라 200 판정 보류."""
    design = {k: v for k, v in BAD.items() if k != "spring_n"}
    r = client.post("/satisfy", json={"design": design, "require": ["RB_NoChatter"], "categories": ["떨림"]})
    assert r.status_code == 200
    assert r.json()["satisfies"] is None
    assert r.json()["pending_reason"] == "missing_required"


def test_회귀_ext_range(client: TestClient) -> None:
    body = client.post(
        "/validate/shacl",
        json={
            "concepts": [{"label": "경도", "type": "Attribute"}, {"label": "겨울철", "type": "EnvCondition"}],
            "relations": [{"subject": "경도", "predicate": "causes", "object": "겨울철"}],
        },
    ).json()
    ValidateResponse.model_validate(body)
    assert body["conforms"] is False
    assert body["violations"][0]["code"] == "causes_range"
    assert body["violations"][0]["severity"] == "violation"  # amber + 저장 차단


def test_회귀_rag_verified_only(client: TestClient) -> None:
    body = client.post("/rag/search", json={"query": "겨울에 고무 블레이드를 쓰면 어떻게 되나?", "k": 6}).json()
    RagSearchResponse.model_validate(body)
    assert body["sufficient"] is True
    assert any(h["sentence"] == "S1" for h in body["hits"])


def test_CD9_mitigate_문장도_검증된_근거다(client: TestClient) -> None:
    """S2(실리콘→소음 해소)는 게이트가 없지만 AC-2 가 요구하는 근거다."""
    body = client.post("/rag/search", json={"query": "실리콘은 소음에 어떤가?", "k": 6}).json()
    s2 = next((h for h in body["hits"] if h["sentence"] == "S2"), None)
    assert s2 is not None, "S2 가 검색되지 않음"
    assert s2["derives_rule"] == "SiliconeRule"
    assert s2["verified"] is True  # CD-9: mitigate 도 컴파일된 규칙이면 검증됨


def test_CD9_지식범위_밖_문장은_미검증이다(client: TestClient) -> None:
    """프로젝트 B(떨림만) 에서 소음 문장은 근거로 쓰일 수 없다 (CD-4 + CD-9)."""
    body = client.post(
        "/rag/search", json={"query": "겨울에 고무 블레이드를 쓰면?", "k": 6, "project_id": "proj-vibration-lab"}
    ).json()
    by_code = {h["sentence"]: h["verified"] for h in body["hits"]}
    noise_sentences = [c for c in ("S1", "S2") if c in by_code]
    assert noise_sentences, "소음 문장이 검색되지 않아 판정 불가"
    assert all(by_code[c] is False for c in noise_sentences)


# ── 에러 모델 일관성 (error_model.md §1) ─────────────────────────────────
CONTRACT_ERROR_KEYS = {"code", "user_message", "trace_id"}


def _assert_contract_error(body: dict, expected_code: str) -> None:
    assert CONTRACT_ERROR_KEYS <= set(body), f"계약 밖 에러 형태: {body}"
    assert body["code"] == expected_code
    assert "detail" not in body, "FastAPI 기본 형태(detail)가 새어 나옴"


def test_스키마_위반은_계약_에러_형태다(client: TestClient) -> None:
    """FastAPI 기본 핸들러는 {'detail': [...]} 를 뱉는다. 그게 새어 나가면 안 된다."""
    r = client.post("/satisfy", json={"design": {"material": "Rubber", "vehicle": "MidSizeSUV", "length_mm": -5}})
    assert r.status_code == 422
    _assert_contract_error(r.json(), "VALIDATION_ERROR")
    assert r.json()["details"]["fields"] == ["design.length_mm"]  # 어느 필드인지 짚어 준다


def test_본문_파싱_실패도_계약_에러_형태다(client: TestClient) -> None:
    r = client.post("/satisfy", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 422)
    _assert_contract_error(r.json(), "VALIDATION_ERROR")


def test_없는_경로는_계약_에러_형태다(client: TestClient) -> None:
    r = client.get("/그런거_없음")
    assert r.status_code == 404
    _assert_contract_error(r.json(), "NOT_FOUND")


def test_승인되지_않은_저장은_거부된다(client: TestClient) -> None:
    """HITL 게이트 — approved=false 는 스키마 단계에서 막힌다."""
    r = client.post(
        "/kg/save",
        json={"sentence_text": "x", "concepts": [], "relations": [], "category": "소음", "approved": False},
    )
    assert r.status_code == 422
    _assert_contract_error(r.json(), "VALIDATION_ERROR")


# ── 읽기 전용 게이트 (06) ─────────────────────────────────────────────────
def test_sparql_은_읽기_전용이다(client: TestClient) -> None:
    ok = client.post("/sparql", json={"query": "SELECT ?s WHERE { ?s a <http://ex.org/domain#KnowledgeSentence> }"})
    assert ok.status_code == 200

    bad = client.post("/sparql", json={"query": 'INSERT DATA { <http://x> <http://y> "z" }'})
    assert bad.status_code == 422
    assert bad.json()["code"] == "VALIDATION_ERROR"


def test_리터럴_안의_INSERT_는_막지_않는다(client: TestClient) -> None:
    """게이트가 문자열 매칭이면 이 쿼리를 잘못 거부한다."""
    r = client.post("/sparql", json={"query": 'SELECT ?s WHERE { ?s ?p "INSERT DATA" }'})
    assert r.status_code == 200


# ── 지식범위 (06 + 04) ────────────────────────────────────────────────────
def test_지식범위_게이트_수(client: TestClient) -> None:
    both = client.post("/rules/compile", json={"categories": ["소음", "떨림"]}).json()
    chatter = client.post("/rules/compile", json={"categories": ["떨림"]}).json()
    assert len(both["shapes"]) == 4
    assert len(chatter["shapes"]) == 3
    assert both["applied_categories"] == ["소음", "떨림"]  # 가나다순이 아니라 문장 번호 순

    # 규칙 5개가 전부 컴파일되지만 게이트는 4개다 — mitigate 인 SiliconeRule 은 게이트를 만들지 않는다.
    # 이 구분이 CD-9 의 핵심: 게이트가 아니어도 검증된 지식이다.
    assert len(both["rules"]) == 5
    assert "SiliconeRule" not in both["gate_rules"]
    assert {"NoiseRule", "ChatterRule", "SpringRule", "ArmRule"} == set(both["gate_rules"])
