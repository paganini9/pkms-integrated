"""T-94 — 타입 판정의 진실원은 온톨로지다 (LLM type 은 힌트).

포스트-g3 실 검증: Solar·Claude 둘 다 `블레이드`를 `Component` 로 줬는데 온톨로지는
`dom:WiperBlade ⊑ ext:PartType` 이라 `hasMaterial` 도메인 위반이 났다 → "고무 블레이드" 지식은
**어떤 provider 로도 저장 불가**였다. 검증기가 LLM 이 붙인 타입으로 판정했기 때문이다.
"""
from __future__ import annotations

import pytest

from reasoning.spec_validate import SpecValidator
from schemas.models import Concept, Relation


@pytest.fixture(scope="module")
def validator() -> SpecValidator:
    return SpecValidator()


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("블레이드", "PartType"),  # dom:WiperBlade ⊑ ext:PartType (LLM 은 Component 라 함)
        ("고무", "Material"),
        ("겨울철", "EnvCondition"),
        ("소음", "Symptom"),  # Symptom ⊑ FailureBehavior ⊑ Behavior 중 가장 구체적인 것
        ("중형 SUV", "VehicleType"),
        ("암", "Component"),  # dom:WiperArm ⊑ ext:Component
    ],
)
def test_온톨로지_canonical_type(validator: SpecValidator, label: str, expected: str) -> None:
    assert validator.canonical_type(label) == expected


def test_모르는_라벨은_None_OOV_경로(validator: SpecValidator) -> None:
    assert validator.canonical_type("타이어") is None
    assert validator.canonical_type("오존") is None


def test_LLM_오타이핑이어도_온톨로지_타입으로_판정한다(validator: SpecValidator) -> None:
    """블레이드=Component(LLM) 여도 hasMaterial 주어 제약(PartType)을 통과해야 한다."""
    concepts = [
        Concept(label="블레이드", type="Component"),  # ← LLM 오타이핑
        Concept(label="고무", type="Material"),
        Concept(label="소음", type="Symptom"),
    ]
    relations = [
        Relation(subject="블레이드", predicate="hasMaterial", object="고무"),
        Relation(subject="고무", predicate="causes", object="소음"),
    ]
    violations = validator.validate(concepts, relations)
    blocking = [v for v in violations if v.severity == "violation"]
    assert blocking == [], f"온톨로지 타입으로 판정했다면 차단이 없어야 한다: {blocking}"


def test_진짜_위반은_여전히_차단된다(validator: SpecValidator) -> None:
    """온톨로지 타입을 써도 range 위반(causes 대상이 증상이 아님)은 그대로 위반이다."""
    concepts = [Concept(label="고무", type="Material"), Concept(label="실리콘", type="Material")]
    relations = [Relation(subject="고무", predicate="causes", object="실리콘")]
    violations = validator.validate(concepts, relations)
    assert any(v.code == "causes_range" and v.severity == "violation" for v in violations)


def test_OOV_는_LLM_힌트로_판정_fail_closed(validator: SpecValidator) -> None:
    """온톨로지가 모르는 개념은 여전히 unknown_concept 경고 + LLM 타입으로 제약 판정."""
    concepts = [Concept(label="타이어", type="Material"), Concept(label="마모", type="Material")]
    relations = [Relation(subject="타이어", predicate="causes", object="마모")]
    violations = validator.validate(concepts, relations)
    assert {v.code for v in violations} >= {"unknown_concept", "causes_range"}
