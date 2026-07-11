"""T-55 (Phase 2) — 04 그래프코어 신설 엔드포인트: 상위 온톨로지 · 규칙 조회.

일관성 검사는 신설하지 않았음을 확인한다(기존 /reason/consistency 재사용 — 계약 §1.2).
음성 테스트: 미승인 상위 온톨로지 변경 → 409, 없는 규칙 impact → 404.
"""
from __future__ import annotations

import pytest

from reasoning.rule_views import RuleViews
from reasoning.satisfy import SatisfyEngine
from reasoning.upper_ontology import UpperOntology
from schemas.errors import GuardrailBlocked, NotFound


@pytest.fixture()
def uo(tmp_path) -> UpperOntology:
    # 오버레이는 tmp 로 격리한다(실 data/ 오염 방지, T-85).
    return UpperOntology(overlay_path=tmp_path / "upper_overlay.ttl")


@pytest.fixture(scope="module")
def views() -> RuleViews:
    return RuleViews(SatisfyEngine())


# ── 상위 온톨로지 조회 (FR-12) ──────────────────────────────────────────────
def test_upper_classes_tree(uo: UpperOntology) -> None:
    out = uo.classes()
    ids = {c["id"] for c in out["classes"]}
    assert "Symptom" in ids
    sym = next(c for c in out["classes"] if c["id"] == "Symptom")
    assert sym["parent"] == "FailureBehavior"  # ext:Symptom rdfs:subClassOf ext:FailureBehavior
    # 관계: causes 의 range 는 Symptom 상위(FailureBehavior)
    rels = {r["id"]: r for r in out["relations"]}
    assert "causes" in rels
    assert rels["causes"]["range"] == "FailureBehavior"


# ── 편집 HITL 게이트 (음성) ─────────────────────────────────────────────────
def test_upper_edit_requires_approval(uo: UpperOntology) -> None:
    with pytest.raises(GuardrailBlocked):
        uo.edit([{"op": "add", "id": "Vibration", "parent": "Symptom"}], approved=False)


def test_upper_edit_approved_accepts(uo: UpperOntology) -> None:
    out = uo.edit([{"op": "add", "id": "Vibration", "parent": "Symptom"}], approved=True)
    assert out["applied"] == 1
    assert out["persisted"] is True


def test_upper_edit_persists_across_restart(tmp_path) -> None:
    """T-85 — 승인 편집이 오버레이 TTL 에 영속돼 재기동(새 인스턴스) 후에도 유지된다."""
    overlay = tmp_path / "upper_overlay.ttl"
    UpperOntology(overlay_path=overlay).edit(
        [{"op": "add", "id": "Vibration", "parent": "Symptom"}], approved=True
    )
    assert overlay.exists(), "오버레이 파일이 생성되지 않았다"

    # 재기동 흉내: 새 인스턴스가 같은 오버레이를 읽는다.
    fresh = UpperOntology(overlay_path=overlay)
    ids = {c["id"] for c in fresh.classes()["classes"]}
    assert "Vibration" in ids, "재기동 후 승인 편집이 사라졌다"
    vib = next(c for c in fresh.classes()["classes"] if c["id"] == "Vibration")
    assert vib["parent"] == "Symptom"  # 부모 subClassOf 반영


def test_upper_edit_unsupported_op_rejected(uo: UpperOntology) -> None:
    from schemas.errors import ValidationError

    with pytest.raises(ValidationError):
        uo.edit([{"op": "delete", "id": "Symptom"}], approved=True)


def test_oov_altlabel_승인_영속_접지(tmp_path) -> None:
    """T-89 part4 — 승인된 altLabel 이 오버레이에 영속돼, 새 SpecValidator(재기동) 접지에 잡힌다."""
    from reasoning.spec_validate import SpecValidator

    overlay = tmp_path / "upper_overlay.ttl"
    assert SpecValidator(overlay_path=overlay).concept_in_domain("발수코팅") is False  # 편입 전
    out = UpperOntology(overlay_path=overlay).approve_altlabel("WiperBlade", "발수코팅", approved=True)
    assert out["persisted"] is True
    # 재기동 흉내: 새 검증기가 오버레이를 읽어 접지.
    assert SpecValidator(overlay_path=overlay).concept_in_domain("발수코팅") is True
    # 미승인은 409, 잘못된 개념은 422.
    with pytest.raises(GuardrailBlocked):
        UpperOntology(overlay_path=overlay).approve_altlabel("WiperBlade", "x", approved=False)
    from schemas.errors import ValidationError

    with pytest.raises(ValidationError):
        UpperOntology(overlay_path=overlay).approve_altlabel("없는개념XYZ", "y", approved=True)


# ── 영향 분석 (AC-6) — 진짜 구조 분석이다 ────────────────────────────────────
def test_upper_impact_material_hits_designs(uo: UpperOntology) -> None:
    out = uo.impact([{"id": "Material"}])
    assert set(out["affected_m1"]) == {"S1", "S2"}  # 재질을 언급하는 문장
    assert set(out["affected_m2"]) == {"Blade_bad", "Blade_good"}  # 재질을 가진 설계


def test_upper_impact_symptom_hits_sentences(uo: UpperOntology) -> None:
    out = uo.impact([{"id": "Symptom"}])
    assert set(out["affected_m1"]) == {"S1", "S2", "S3", "S4", "S5", "S6"}
    assert set(out["affected_m2"]) == {"RB_Winter", "RB_NoChatter"}  # 증상을 금지하는 요구


def test_upper_impact_is_sorted_deterministic(uo: UpperOntology) -> None:
    a = uo.impact([{"id": "Symptom"}])
    b = uo.impact([{"id": "Symptom"}])
    assert a["affected_m1"] == b["affected_m1"] == sorted(a["affected_m1"], key=lambda s: int(s[1:]))


# ── 규칙 조회 (읽기 전용 — FR-13) ───────────────────────────────────────────
def test_rules_list_view(views: RuleViews) -> None:
    out = views.list()
    assert len(out["rules"]) == 5
    assert sorted(out["shapes"]) == ["ArmShape", "ChatterShape", "NoiseShape", "SpringShape"]
    assert any("실리콘" in h for h in out["human_view"])  # mitigate 규칙도 뷰에 남는다


def test_rules_impact_fires_on_real_designs(views: RuleViews) -> None:
    """ChatterRule 게이트는 Blade_bad(600 > SUV 599)에서 실제로 발화한다 — 근사가 아니다."""
    out = views.impact("ChatterRule")
    assert out["affected_instances"] == ["Blade_bad"]


def test_rules_impact_mitigate_has_no_gate(views: RuleViews) -> None:
    """게이트 없는 mitigate 규칙(SiliconeRule)은 발화 대상이 없다(빈 목록)."""
    assert views.impact("SiliconeRule")["affected_instances"] == []


# ── 음성: 없는 규칙 ──────────────────────────────────────────────────────────
def test_rules_impact_unknown_is_404(views: RuleViews) -> None:
    with pytest.raises(NotFound):
        views.impact("존재하지않는규칙")


def test_rules_view_has_no_write_surface() -> None:
    """규칙은 문장 파생물(FR-3d) — PUT/PATCH 표면이 없어야 한다."""
    from reasoning import routes

    methods = set()
    for route in routes.router.routes:
        if getattr(route, "path", "").startswith("/rules"):
            methods |= set(route.methods)
    assert "PUT" not in methods and "PATCH" not in methods
