"""T-93 — 저작 루프 라이브: 저작한 지식이 **satisfy 판정에 실제로 반영된다**.

포스트-g3 실 검증이 드러낸 구멍: K2(오존→균열)를 완전히 접지·저장해도 `/rules` 는 시드 5개
그대로였고 satisfy 판정은 한 글자도 바뀌지 않았다. 규칙은 시드 `rules.ttl` 에서만 컴파일되고,
저장 응답의 `derived` 는 영속되지 않는 일회용 투영이었기 때문이다.

여기서 그 루프를 닫는다:
  거버넌스 승인(Ozone·Crack) → K2 저작·저장 → 규칙 파생·오버레이 영속 → 컴파일 → **satisfy 판정 변화**.

하드 게이트: **오버레이가 비면 시드 회귀는 한 글자도 달라지지 않는다.**
"""
from __future__ import annotations

import pytest

from core.config import settings
from reasoning.authoring import AuthoringRuleStore
from reasoning.causation import CausationReifier
from reasoning.compiler import RuleCompiler
from reasoning.satisfy import SatisfyEngine
from reasoning.spec_validate import SpecValidator
from reasoning.upper_ontology import UpperOntology
from schemas.models import Design, SaveRequest
from store.kg import KgService
from store.oxigraph import OxigraphStore

# K2 — "오존 노출이 기준을 초과하면 고무 블레이드에 균열이 생긴다." (실 검증에서 Claude 가 뽑은 추출안)
K2_TEXT = "오존 노출이 기준을 초과하면 고무 블레이드에 균열이 생긴다."
K2_CONCEPTS = [
    {"label": "오존", "type": "EnvCondition"},
    {"label": "블레이드", "type": "Component"},  # ← LLM 오타이핑(실측). T-94 가 PartType 으로 해석한다.
    {"label": "고무", "type": "Material"},
    {"label": "균열", "type": "Symptom"},
]
K2_RELATIONS = [
    {"subject": "블레이드", "predicate": "hasMaterial", "object": "고무"},
    {"subject": "고무", "predicate": "causes", "object": "균열"},
    {"subject": "균열", "predicate": "conditionedOn", "object": "오존"},
]

#: 오존 환경에서 쓰이는 고무 블레이드 설계 (CD-15 — env 는 닫힌 enum 이 아니다)
DESIGN_OZONE = Design(
    id="D-ozone", material="Rubber", vehicle="MidSizeSUV", length_mm=550, spring_n=12,
    arm_shape="complex", env="Ozone",
)


@pytest.fixture()
def env(tmp_path, monkeypatch):  # noqa: ANN001, ANN201
    """시드 온톨로지 + 빈 오버레이(상위·저작) 로 격리된 스택."""
    overlay = tmp_path / "upper_overlay.ttl"
    authoring = tmp_path / "authoring_rules.ttl"
    monkeypatch.setattr(settings, "upper_overlay_path", overlay)
    monkeypatch.setattr(settings, "authoring_rules_path", authoring)

    store = OxigraphStore(tmp_path / "oxigraph")
    store.load_seed([p for p in settings.seed_ttl if p.exists()])

    class _Spy:
        def upsert(self, items):  # noqa: ANN001, ANN201
            return len(items)

        def delete(self, iris):  # noqa: ANN001, ANN201
            return len(iris)

    return {
        "store": store,
        "authoring": AuthoringRuleStore(authoring),
        "upper": UpperOntology(overlay_path=overlay),
        "overlay": overlay,
        "retriever": _Spy(),
        "tmp": tmp_path,
    }


def _validator(env) -> SpecValidator:  # noqa: ANN001
    return SpecValidator(overlay_path=env["overlay"])


def _approve_new_concepts(upper: UpperOntology) -> None:
    """거버넌스: 신규 개념 편입(승인) — 실 검증에서 실제로 작동을 확인한 경로."""
    upper.edit([{"op": "add", "id": "Ozone", "parent": "EnvCondition"},
                {"op": "add", "id": "Crack", "parent": "Symptom"}], approved=True)
    upper.approve_altlabel("http://ex.org/spmm-ext#Ozone", "오존", approved=True)
    upper.approve_altlabel("http://ex.org/spmm-ext#Crack", "균열", approved=True)


def _kg(env, validator: SpecValidator) -> KgService:  # noqa: ANN001
    return KgService(
        env["store"],
        retriever=env["retriever"],
        authoring_store=env["authoring"],
        reifier=CausationReifier(validator),
    )


# ── 하드 게이트: 오버레이가 비면 시드는 한 글자도 달라지지 않는다 ─────────────
def test_빈_오버레이면_시드_규칙_불변(env) -> None:  # noqa: ANN001
    compiler = RuleCompiler(authoring_rules_path=env["authoring"].path)
    assert sorted(r.id for r in compiler.rules) == [
        "ArmRule", "ChatterRule", "NoiseRule", "SiliconeRule", "SpringRule"
    ]


def test_빈_오버레이면_satisfy_시드_회귀_불변(env) -> None:  # noqa: ANN001
    engine = SatisfyEngine(RuleCompiler(authoring_rules_path=env["authoring"].path))
    bad = Design(material="Rubber", length_mm=600, spring_n=8, arm_shape="simple",
                 vehicle="MidSizeSUV", env="Winter")
    good = Design(material="Silicone", length_mm=550, spring_n=12, arm_shape="complex",
                  vehicle="CompactSedan", env="Winter")
    assert engine.satisfy(bad, []).violations == ["S1", "S3", "S4", "S6"]  # sat-bad
    assert engine.satisfy(good, []).satisfies is True  # sat-good


# ── 라이브 증명: K2 저작 전후로 satisfy 판정이 바뀐다 ────────────────────────
def test_K2_저작_전후_satisfy_판정이_바뀐다(env) -> None:  # noqa: ANN001
    _approve_new_concepts(env["upper"])
    validator = _validator(env)

    compiler = RuleCompiler(authoring_rules_path=env["authoring"].path)
    engine = SatisfyEngine(compiler)

    # (1) 저작 전 — 오존 설계는 아무 증상도 내지 않는다(시드는 오존을 모른다).
    before = engine.satisfy(DESIGN_OZONE, [])
    assert before.satisfies is True
    assert before.steps[2].exhibited == []

    # (2) K2 저작 — 접지·검증 통과(블레이드 오타이핑은 T-94 가 해석) → 저장.
    req = SaveRequest(sentence_text=K2_TEXT, concepts=K2_CONCEPTS, relations=K2_RELATIONS,
                      category="소음", approved=True, draft_id="t93-k2")
    assert [v for v in validator.validate(req.concepts, req.relations) if v.severity == "violation"] == []
    saved = _kg(env, validator).save(req)

    # 파생 규칙이 문장별 고유 id 로, 증상은 **균열**(카테고리가 아니라)로 붙는다.
    assert saved.derived.rule.id == f"{saved.sentence.id}Rule"
    assert saved.derived.rule.about_symptom == "Crack"
    assert sorted((c.path, c.val) for c in saved.derived.rule.conds) == [
        ("hasMaterial", "Rubber"), ("operatesIn", "Ozone")
    ]

    # (3) 저작 후 — **같은 설계**의 판정이 달라진다: 오존+고무 → 균열(Crack) 유발.
    after = engine.satisfy(DESIGN_OZONE, [])
    assert [e.symptom for e in after.steps[2].exhibited] == ["Crack"], "저작 지식이 판정에 반영되지 않았다"
    assert after.steps[2].ok is False  # 무증상 규칙 실패 — 저작 전엔 통과였다
    assert any("Crack" in j for j in after.justification)
    assert saved.sentence.id in after.steps[2].exhibited[0].sentences  # 근거는 저작 문장

    # 저작 규칙이 실제로 컴파일 게이트가 되었는가(시드 5 + 저작 1)
    assert f"{saved.sentence.id}Rule" in {r.id for r in compiler.rules}

    # 최종 `satisfies` 플립은 **그 증상을 금지하는 요구(RB)** 가 있어야 한다 — 요구 없는 증상은
    # 요구 위반이 아니다(RB 가 판정의 기준이다). 신규 증상의 RB 등록은 M2 경로(2단계) 소관이다.
    assert after.satisfies is True
    assert after.violated_requirements == []


def test_저작_규칙은_오버레이에_영속된다(env) -> None:  # noqa: ANN001
    """재기동(새 컴파일러 인스턴스)해도 저작 규칙이 살아 있다 — T-85 오버레이 패턴."""
    _approve_new_concepts(env["upper"])
    validator = _validator(env)
    _kg(env, validator).save(
        SaveRequest(sentence_text=K2_TEXT, concepts=K2_CONCEPTS, relations=K2_RELATIONS,
                    category="소음", approved=True, draft_id="t93-persist")
    )
    assert env["authoring"].path.exists()

    fresh = RuleCompiler(authoring_rules_path=env["authoring"].path)  # 재기동 흉내
    authored = [r for r in fresh.rules if r.symptom == "Crack"]
    assert len(authored) == 1
    assert authored[0].category == "소음"  # CD-4 카테고리 스코프 유지


def test_카테고리_스코프_밖이면_저작_규칙도_컴파일되지_않는다(env) -> None:  # noqa: ANN001
    """CD-4 — 프로젝트 지식범위 필터는 저작 규칙에도 그대로 적용된다."""
    _approve_new_concepts(env["upper"])
    validator = _validator(env)
    _kg(env, validator).save(
        SaveRequest(sentence_text=K2_TEXT, concepts=K2_CONCEPTS, relations=K2_RELATIONS,
                    category="소음", approved=True, draft_id="t93-scope")
    )
    engine = SatisfyEngine(RuleCompiler(authoring_rules_path=env["authoring"].path))
    scoped = engine.satisfy(DESIGN_OZONE, [], categories={"떨림"})  # 소음 범위 밖
    assert scoped.satisfies is True, "지식범위 밖 저작 규칙이 판정에 새어 들어갔다"


def test_같은_사실을_다시_저작해도_규칙은_하나(env) -> None:  # noqa: ANN001
    """등가 규칙(증상·극성·조건 동일)은 재사용한다 — 게이트가 둘로 늘면 같은 위반이 두 번 잡힌다."""
    _approve_new_concepts(env["upper"])
    validator = _validator(env)
    kg = _kg(env, validator)
    first = kg.save(SaveRequest(sentence_text=K2_TEXT, concepts=K2_CONCEPTS, relations=K2_RELATIONS,
                                category="소음", approved=True, draft_id="t93-dup-1"))
    second = kg.save(SaveRequest(sentence_text="오존 환경의 고무 블레이드는 균열이 생긴다.",
                                 concepts=K2_CONCEPTS, relations=K2_RELATIONS,
                                 category="소음", approved=True, draft_id="t93-dup-2"))
    assert second.derived.rule.id == first.derived.rule.id  # 새 규칙을 만들지 않았다
    assert len([r for r in env["authoring"].rules() if r.symptom == "Crack"]) == 1


def test_요구가_균열을_금지하면_최종_satisfies_가_뒤집힌다(env) -> None:  # noqa: ANN001
    """저작 → 게이트 → 증상 → **요구 위반 → satisfies=False** 까지 끝까지 닿는다.

    시드 m2 에는 균열을 금지하는 요구가 없다(신규 증상이니 당연하다). 요구 등록은 M2·RB 경로(2단계)라
    여기서는 **임시 온톨로지 사본**에 RB 를 하나 넣어 최종 판정까지 도달함을 증명한다(시드 불변).
    """
    import shutil

    onto = env["tmp"] / "ontology"
    shutil.copytree(settings.ontology_dir, onto)
    (onto / "m2_instances.ttl").open("a", encoding="utf-8").write(
        "\n@prefix ext2: <http://ex.org/spmm-ext#> .\n"
        "eng:RB_NoCrack a spmm:RequiredBehavior ; rdfs:label \"오존 내구(균열 없음)\" ; "
        "dom:forbidsSymptom ext2:Crack .\n"
    )

    _approve_new_concepts(env["upper"])
    validator = _validator(env)
    saved = _kg(env, validator).save(
        SaveRequest(sentence_text=K2_TEXT, concepts=K2_CONCEPTS, relations=K2_RELATIONS,
                    category="소음", approved=True, draft_id="t93-rb")
    )

    engine = SatisfyEngine(
        RuleCompiler(ontology_dir=onto, authoring_rules_path=env["authoring"].path), ontology_dir=onto
    )
    result = engine.satisfy(DESIGN_OZONE, ["RB_NoCrack"])
    assert result.satisfies is False, "요구가 금지한 증상을 유발했는데 판정이 뒤집히지 않았다"
    assert [v.rb for v in result.violated_requirements] == ["RB_NoCrack"]
    assert result.violations == [saved.sentence.id]  # 근거 = 저작 문장


# ── Causation 배선: 저장 그래프에 실제로 기록된다(0행 금지) ──────────────────
def test_Causation_노드가_저장_그래프에_기록된다(env) -> None:  # noqa: ANN001
    _approve_new_concepts(env["upper"])
    validator = _validator(env)
    saved = _kg(env, validator).save(
        SaveRequest(sentence_text=K2_TEXT, concepts=K2_CONCEPTS, relations=K2_RELATIONS,
                    category="소음", approved=True, draft_id="t93-causation")
    )
    rows = env["store"].query(
        "SELECT ?c ?m ?cond ?s WHERE { "
        "?c a <http://ex.org/spmm-ext#Causation> ; "
        "<http://ex.org/spmm-ext#hasMechanism> ?m ; "
        "<http://ex.org/spmm-ext#underCondition> ?cond ; "
        "<http://ex.org/spmm-ext#manifestsSymptom> ?s }",
        readonly=False,
    )
    assert rows, "Causation 노드가 0행 — T-91 이 런타임에 배선되지 않았다"
    row = rows[0]
    assert row["m"].endswith("Rubber")  # 기전
    assert row["cond"].endswith("Ozone")  # 조건
    assert row["s"].endswith("Crack")  # 증상 — (기전·조건·증상) 바인딩 보존
    # 프로비넌스: 어느 문장에서 왔는가
    prov = env["store"].query(
        f"SELECT ?s WHERE {{ <{row['c']}> <http://ex.org/domain#fromSentence> ?s }}", readonly=False
    )
    assert prov[0]["s"].endswith(saved.sentence.id)
