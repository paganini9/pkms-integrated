"""04 그래프·코어 테스트 — 회귀셋(sat-bad·sat-good·scope-A·scope-B·ext-range·sat-pending) 재현.

이 테스트가 통과해야 G1(인터페이스 적합성)을 선언할 수 있다.
"""
from __future__ import annotations

import pytest
from rdflib import Graph

from reasoning.compiler import RuleCompiler
from reasoning.reasoner import Reasoner, reasoner_status
from reasoning.rules import normalize_violations, sentence_sort_key
from reasoning.satisfy import SatisfyEngine
from reasoning.spec_validate import SpecValidator
from schemas.models import Concept, Design, Relation, SatisfyResponse, ValidateResponse

RB_ALL = ["RB_Winter", "RB_NoChatter"]
BLADE_BAD = Design(
    id="Blade_bad", material="Rubber", length_mm=600, spring_n=8, arm_shape="simple", vehicle="MidSizeSUV", env="Winter"
)
BLADE_GOOD = Design(
    id="Blade_good", material="Silicone", length_mm=550, spring_n=12, arm_shape="complex", vehicle="CompactSedan", env="Winter"
)


@pytest.fixture(scope="module")
def engine() -> SatisfyEngine:
    return SatisfyEngine()


@pytest.fixture(scope="module")
def compiler() -> RuleCompiler:
    return RuleCompiler()


# ── 규칙 컴파일러 · CD-4 ──────────────────────────────────────────────────
def test_게이트_수는_카테고리로_컴파일_시점에_정해진다(compiler: RuleCompiler) -> None:
    assert compiler.gate_count({"소음", "떨림"}) == 4  # AC-scope 프로젝트 A
    assert compiler.gate_count({"떨림"}) == 3  # AC-scope 프로젝트 B — 소음 규칙 미컴파일
    assert compiler.gate_count(None) == 4  # 전체 (mitigate 인 SiliconeRule 은 게이트 없음)


def test_mitigate_규칙은_게이트를_만들지_않는다(compiler: RuleCompiler) -> None:
    compiled = compiler.compile({"소음"})
    assert "SiliconeRule" not in compiled.gate_rules
    assert "NoiseRule" in compiled.gate_rules
    # 하지만 인과엣지·사람뷰에는 남아 근거로 쓰인다
    assert any("실리콘" in h for h in compiled.human_view)


def test_gate_rules_는_03_RAG_의_verified_판정_근거다(compiler: RuleCompiler) -> None:
    assert compiler.compile({"떨림"}).gate_rules == {"ChatterRule", "SpringRule", "ArmRule"}


# ── CD-1 정규화 ───────────────────────────────────────────────────────────
def test_CD1_정규화는_mitigate_문장을_뺀다() -> None:
    polarity = {"S1": "cause", "S3": "cause", "S5": "mitigate", "S4": "cause", "S6": "cause"}
    assert normalize_violations(["S1", "S3,S5", "S4", "S6"], polarity) == ["S1", "S3", "S4", "S6"]


def test_문장_정렬은_숫자_기준이다() -> None:
    assert sorted(["S10", "S2", "S1"], key=sentence_sort_key) == ["S1", "S2", "S10"]


# ── satisfy 회귀 ──────────────────────────────────────────────────────────
def test_회귀_sat_bad(engine: SatisfyEngine) -> None:
    r = engine.satisfy(BLADE_BAD, RB_ALL, {"소음", "떨림"})
    assert r.satisfies is False
    assert r.violations == ["S1", "S3", "S4", "S6"]  # AC-2
    assert r.violation_bases == ["S1", "S3,S5", "S4", "S6"]  # 회귀 scope-A 표기
    assert {v.rb for v in r.violated_requirements} == {"RB_Winter", "RB_NoChatter"}
    assert "재질→실리콘(S2)" in r.alternatives
    assert "길이→차종 안전길이 이내(S5)" in r.alternatives
    SatisfyResponse.model_validate(r.model_dump())


def test_회귀_sat_good(engine: SatisfyEngine) -> None:
    r = engine.satisfy(BLADE_GOOD, RB_ALL, {"소음", "떨림"})
    assert r.satisfies is True
    assert r.violations == [] and r.violation_bases == []
    assert r.alternatives == []
    assert r.steps[0].ok and r.steps[1].ok and r.steps[2].ok


def test_회귀_scope_B_는_소음_규칙이_빠져_3위반(engine: SatisfyEngine) -> None:
    r = engine.satisfy(BLADE_BAD, ["RB_NoChatter"], {"떨림"})
    assert r.satisfies is False
    assert r.violation_bases == ["S3,S5", "S4", "S6"]
    assert r.violations == ["S3", "S4", "S6"]
    assert r.applied_categories == ["떨림"]
    # 소음은 유발되지 않은 것으로 취급된다 (규칙 자체가 컴파일되지 않았으므로)
    assert all(e.symptom != "Noise" for e in r.steps[2].exhibited)


def test_동일_설계라도_지식범위가_다르면_결과가_다르다(engine: SatisfyEngine) -> None:
    """AC-scope 의 핵심 — CD-4 가 지켜지는지."""
    a = engine.satisfy(BLADE_BAD, RB_ALL, {"소음", "떨림"})
    b = engine.satisfy(BLADE_BAD, ["RB_NoChatter"], {"떨림"})
    assert len(a.violations) == 4 and len(b.violations) == 3


def test_수치_누락은_422가_아니라_판정_보류다(engine: SatisfyEngine) -> None:
    """CD-8 — spring_n 결측. 스키마를 통과해 satisfies=null 로 와야 한다."""
    partial = Design(material="Rubber", length_mm=600, arm_shape="simple", vehicle="MidSizeSUV", env="Winter")
    r = engine.satisfy(partial, RB_ALL, {"소음", "떨림"})
    assert r.satisfies is None
    assert r.pending_reason == "missing_required"
    assert r.violations == []  # 부분 정보로 위반을 확정하지 않는다
    warnings = r.steps[1].warnings or []
    assert [w.code for w in warnings] == ["missing_required"]
    assert warnings[0].severity == "warning"  # CD-7: 저장/입력을 막지 않는다


def test_시그니처_캐시(engine: SatisfyEngine) -> None:
    fresh = SatisfyEngine()
    first = fresh.satisfy(BLADE_BAD, RB_ALL, {"소음", "떨림"})
    second = fresh.satisfy(BLADE_BAD, RB_ALL, {"소음", "떨림"})
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.violations == first.violations


def test_pySHACL_이_정본_shapes_를_오염시키지_않는다() -> None:
    """pySHACL 은 넘겨받은 shacl_graph 에 트리플을 주입한다. 정본을 넘기면 안 된다.

    오염되면 (1) shapes_hash 가 매번 달라져 satisfy 캐시가 영원히 빗나가고,
    (2) /rules/compile 의 shapes_ttl 이 호출할수록 부풀어 오른다.
    """
    engine = SatisfyEngine()
    compiled = engine.compiler.compile({"소음", "떨림"})
    before_triples, before_hash = len(compiled.shapes), compiled.shapes_hash

    for _ in range(3):
        engine.satisfy(BLADE_BAD, RB_ALL, {"소음", "떨림"})

    assert len(compiled.shapes) == before_triples, "pySHACL 이 정본 shapes 에 트리플을 주입했다"
    assert compiled.shapes_hash == before_hash


def test_shapes_hash_는_컴파일_시점에_고정된다(compiler: RuleCompiler) -> None:
    compiled = compiler.compile({"떨림"})
    assert compiled.shapes_hash == compiled.shapes_hash
    assert len(compiled.shapes_hash) == 16
    # 다른 지식범위 → 다른 해시 (캐시 키가 범위를 구분해야 한다)
    assert compiled.shapes_hash != compiler.compile({"소음", "떨림"}).shapes_hash


def test_판정은_결정론적이다(engine: SatisfyEngine) -> None:
    """SHACL 리포트 순서에 의존하면 안 된다 (NFR 재현성)."""
    fresh = SatisfyEngine()  # 캐시 없이
    runs = [SatisfyEngine().satisfy(BLADE_BAD, RB_ALL, {"소음", "떨림"}) for _ in range(3)]
    assert all(r.violations == ["S1", "S3", "S4", "S6"] for r in runs)
    assert all(r.violation_bases == runs[0].violation_bases for r in runs)
    assert all(r.alternatives == runs[0].alternatives for r in runs)
    assert fresh.satisfy(BLADE_BAD, RB_ALL, {"소음", "떨림"}).violations == runs[0].violations


# ── 명세 검증 (FR-02 · AC-1) ──────────────────────────────────────────────
def test_회귀_ext_range() -> None:
    """'경도가 겨울철을 유발한다' — causes 의 대상은 증상이어야 한다."""
    v = SpecValidator()
    violations = v.validate(
        [Concept(label="경도", type="Attribute"), Concept(label="겨울철", type="EnvCondition")],
        [Relation(subject="경도", predicate="causes", object="겨울철")],
    )
    assert [x.code for x in violations] == ["causes_range"]
    assert violations[0].offender == "겨울철"
    assert violations[0].severity == "violation"  # CD-7: amber + 저장 차단
    res = ValidateResponse(conforms=False, violations=violations, trace_id="t")
    assert res.conforms is False


def test_정상_추출은_통과한다() -> None:
    v = SpecValidator()
    violations = v.validate(
        [
            Concept(label="겨울철", type="EnvCondition"),
            Concept(label="고무", type="Material"),
            Concept(label="소음", type="Symptom"),
        ],
        [
            Relation(subject="고무", predicate="causes", object="소음"),
            Relation(subject="소음", predicate="conditionedOn", object="겨울철"),
        ],
    )
    assert violations == []


def test_disjoint_위반_검출() -> None:
    v = SpecValidator()
    violations = v.validate(
        [Concept(label="이상한것", type="Symptom"), Concept(label="이상한것", type="Material")], []
    )
    assert [x.code for x in violations] == ["disjoint"]
    assert violations[0].severity == "violation"


def test_개념_목록에_없는_대상은_경고이고_저장을_막지_않는다() -> None:
    v = SpecValidator()
    violations = v.validate(
        [Concept(label="고무", type="Material")],
        [Relation(subject="고무", predicate="causes", object="유령증상")],
    )
    assert [x.code for x in violations] == ["unknown_concept"]
    assert violations[0].severity == "warning"  # CD-7


# ── reasoner ──────────────────────────────────────────────────────────────
def test_JRE_없어도_일관성_검사가_동작한다() -> None:
    r = Reasoner()
    result = r.consistency(r._load_onto())
    assert result.consistent is True
    assert result.clashes == []
    assert result.engine in {"owlrl", "hermit"}


def test_고의_모순을_잡는다() -> None:
    r = Reasoner()
    graph = r._load_onto()
    graph.parse(
        data="""
        @prefix spmm: <http://ex.org/spmm#> .
        @prefix eng: <http://ex.org/eng#> .
        eng:Clash a spmm:Entity , spmm:Behavior .
        """,
        format="turtle",
    )
    result = r.consistency(graph)
    assert result.consistent is False
    assert any("Clash" in c for c in result.clashes)


def test_분류_사슬(compiler: RuleCompiler) -> None:
    types = Reasoner().classify("http://ex.org/eng#Blade_good")
    for expected in ("WiperBlade", "PartType", "Artifact", "Entity"):
        assert expected in types


def test_reasoner_status_는_정직하다() -> None:
    assert reasoner_status() in {"ok", "no_jre"}


# ── dry-run (AC-7) ────────────────────────────────────────────────────────
def test_dry_run_안전길이_599_to_595(engine: SatisfyEngine) -> None:
    """SUV 안전길이를 595 로 낮추면 어떤 설계가 새로 위반하는가."""
    override = Graph().parse(
        data="""
        @prefix dom: <http://ex.org/domain#> .
        dom:MidSizeSUV dom:maxSafeLengthMm 595 .
        """,
        format="turtle",
    )
    new_violations, affected = engine.dry_run(override, {"소음", "떨림"})
    # Blade_bad(600mm)는 599 기준으로도 이미 위반이라 "새 위반"이 아니다.
    # 새 위반이 생기려면 596~599 구간의 설계가 있어야 한다 → 지금 시드엔 없다.
    assert affected == [] and new_violations == []


def test_dry_run_안전길이를_540으로_낮추면_설계B가_새로_위반한다(engine: SatisfyEngine) -> None:
    override = Graph().parse(
        data="""
        @prefix dom: <http://ex.org/domain#> .
        dom:CompactSedan dom:maxSafeLengthMm 540 .
        """,
        format="turtle",
    )
    new_violations, affected = engine.dry_run(override, {"소음", "떨림"})
    assert "Blade_good" in affected  # 550mm > 540
    assert any("S3,S5" in v for v in new_violations)
