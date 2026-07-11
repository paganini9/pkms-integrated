"""T-91 — 조건부 인과 reification 게이트.

하드 게이트: **기존 satisfy 회귀 전건 재통과**(리팩터-그린) — Causation 추가는 설계-satisfy 경로에
영향을 주지 않아야 한다. 그 위에 reification 의 정확성(바인딩 보존·실패문장 저장·shape)을 검증한다.
"""
from __future__ import annotations

import pytest
from rdflib import RDF, Namespace

from reasoning.causation import CausationNode, CausationReifier
from reasoning.compiler import RuleCompiler, causation_shape_graph
from reasoning.reasoner import disjoint_clashes, expand
from reasoning.satisfy import SatisfyEngine
from schemas.models import Concept, Design, Relation

EXT = Namespace("http://ex.org/spmm-ext#")
DOM = Namespace("http://ex.org/domain#")
SH = Namespace("http://www.w3.org/ns/shacl#")

_SOUND = {"소음", "떨림"}
_CHATTER = {"떨림"}


# ── 하드 게이트: satisfy 회귀 불변 (Causation 은 설계-satisfy 경로를 건드리지 않는다) ──────────
@pytest.fixture(scope="module")
def engine() -> SatisfyEngine:
    return SatisfyEngine()


def test_satisfy_회귀_sat_bad_불변(engine: SatisfyEngine) -> None:
    d = Design(material="Rubber", length_mm=600, spring_n=8, arm_shape="simple", vehicle="MidSizeSUV", env="Winter")
    r = engine.satisfy(d, ["RB_Winter", "RB_NoChatter"], _SOUND)
    assert r.satisfies is False
    assert r.violations == ["S1", "S3", "S4", "S6"]
    assert r.violation_bases == ["S1", "S3,S5", "S4", "S6"]


def test_satisfy_회귀_sat_good_불변(engine: SatisfyEngine) -> None:
    d = Design(material="Silicone", length_mm=550, spring_n=12, arm_shape="complex", vehicle="CompactSedan", env="Winter")
    r = engine.satisfy(d, ["RB_Winter", "RB_NoChatter"], _SOUND)
    assert r.satisfies is True
    assert r.violations == []


def test_satisfy_회귀_sat_pending_불변(engine: SatisfyEngine) -> None:
    d = Design(material="Rubber", length_mm=600, arm_shape="simple", vehicle="MidSizeSUV", env="Winter")
    r = engine.satisfy(d, ["RB_NoChatter"], _CHATTER)
    assert r.satisfies is None
    assert r.pending_reason == "missing_required"


def test_satisfy_회귀_scope_B_불변(engine: SatisfyEngine) -> None:
    d = Design(material="Rubber", length_mm=600, spring_n=8, arm_shape="simple", vehicle="MidSizeSUV", env="Winter")
    r = engine.satisfy(d, ["RB_NoChatter"], _CHATTER)
    assert r.satisfies is False
    assert r.violations == ["S3", "S4", "S6"]
    assert r.violation_bases == ["S3,S5", "S4", "S6"]


# ── 컴파일러: Causation 노드 + shape 동시 방출 (단일 소스 = rules.ttl, 손 SHACL 아님) ─────────
def test_컴파일러_causation_동시방출() -> None:
    c = RuleCompiler().compile()
    # 설계-satisfy 경로는 그대로 (게이트 4개)
    assert set(c.gates) == {"ArmShape", "ChatterShape", "NoiseShape", "SpringShape"}
    # 규칙당 Causation 노드 하나 (5 규칙)
    nodes = list(c.causation.subjects(RDF.type, EXT.Causation))
    assert len(nodes) == len(c.applied_rules) == 5
    # S1 인과: (Rubber, Winter, Noise, cause) — 실패 문장의 정본 표현
    noise = DOM["Causation_NoiseRule"]
    assert c.causation.value(noise, EXT.hasMechanism) == DOM.Rubber
    assert c.causation.value(noise, EXT.underCondition) == DOM.Winter
    assert c.causation.value(noise, EXT.manifestsSymptom) == DOM.Noise
    # Causation shape 도 방출됐다(targetClass = Causation)
    assert (DOM.CausationShape, None, None) in c.causation_shape
    assert len(c.causation_shape) > 0


def test_causation_노드는_카테고리_스코프를_따른다() -> None:
    """CD-4: 지식범위 필터가 Causation 방출에도 적용된다(소음만 → NoiseRule·SiliconeRule)."""
    c = RuleCompiler().compile({"소음"})
    syms = {str(c.causation.value(n, EXT.manifestsSymptom)) for n in c.causation.subjects(RDF.type, EXT.Causation)}
    assert syms == {str(DOM.Noise)}


# ── Causation shape: 적합 / 거부 ──────────────────────────────────────────────
@pytest.fixture(scope="module")
def reifier() -> CausationReifier:
    return CausationReifier()


def test_causation_shape_적합(reifier: CausationReifier) -> None:
    n = CausationNode(iri=DOM["_ok"], mechanism=DOM.Rubber, condition=DOM.Winter, symptom=DOM.Noise, polarity="cause")
    assert reifier.validate([n]) == []


def test_causation_shape_증상누락_거부(reifier: CausationReifier) -> None:
    n = CausationNode(iri=DOM["_bad"], mechanism=DOM.Rubber, condition=DOM.Winter, symptom=None, polarity="cause")
    assert reifier.validate([n]), "증상 없는 Causation 은 위반이어야 한다"


def test_causation_shape_증상타입_거부(reifier: CausationReifier) -> None:
    # 증상 자리에 EnvCondition(Winter) → sh:class Symptom 위반
    n = CausationNode(iri=DOM["_bad2"], mechanism=DOM.Rubber, condition=None, symptom=DOM.Winter, polarity="cause")
    assert reifier.validate([n])


def test_causation_shape_조건타입_거부(reifier: CausationReifier) -> None:
    # 조건 자리에 Symptom(Noise) → sh:class EnvCondition 위반
    n = CausationNode(iri=DOM["_bad3"], mechanism=DOM.Rubber, condition=DOM.Noise, symptom=DOM.Noise, polarity="cause")
    assert reifier.validate([n])


# ── 실패 문장: conditionedOn 위반 소멸 · Causation 으로 깨끗이 저장 ─────────────────────────
def _sentence_frame() -> tuple[list[Concept], list[Relation]]:
    """'겨울철 저온에서 고무 블레이드는 소음이 발생한다' 의 인과 프레임(증상 앵커 조건)."""
    concepts = [
        Concept(label="블레이드", type="PartType"), Concept(label="고무", type="Material"),
        Concept(label="겨울철 저온", type="EnvCondition"), Concept(label="소음", type="Symptom"),
    ]
    relations = [
        Relation(subject="블레이드", predicate="hasMaterial", object="고무"),
        Relation(subject="블레이드", predicate="causes", object="소음"),
        Relation(subject="소음", predicate="conditionedOn", object="겨울철 저온"),
    ]
    return concepts, relations


def test_실패문장_인과프레임_reify_저장가능(reifier: CausationReifier) -> None:
    concepts, relations = _sentence_frame()
    nodes = reifier.reify(concepts, relations)
    assert len(nodes) == 1
    n = nodes[0]
    assert n.mechanism == DOM.WiperBlade and n.condition == DOM.Winter and n.symptom == DOM.Noise
    assert reifier.validate(nodes) == [], "인과 프레임 Causation 은 위반 없이 저장 가능해야 한다"


def test_옛_부품앵커_conditionedOn_은_여전히_위반() -> None:
    """대조군: 부품(PartType)을 conditionedOn 주어로 두면 도메인 위반(이슈2b) — 프레임을 안 쓴 옛 케이스."""
    from reasoning.spec_validate import SpecValidator

    v = SpecValidator()
    concepts = [Concept(label="블레이드", type="PartType"), Concept(label="겨울철 저온", type="EnvCondition")]
    rels = [Relation(subject="블레이드", predicate="conditionedOn", object="겨울철 저온")]
    viols = [x for x in v.validate(concepts, rels) if x.severity == "violation"]
    assert any(x.source_shape == "ConditionedonDomainShape" for x in viols)


# ── 다맥락 바인딩 보존: 한 증상에 두 (기전) 맥락 → 노드 2개, 안 섞임 ─────────────────────────
def test_다맥락_바인딩_보존(reifier: CausationReifier) -> None:
    concepts = [
        Concept(label="고무", type="Material"), Concept(label="실리콘", type="Material"),
        Concept(label="겨울철 저온", type="EnvCondition"), Concept(label="소음", type="Symptom"),
    ]
    rels = [
        Relation(subject="고무", predicate="causes", object="소음"),
        Relation(subject="소음", predicate="conditionedOn", object="겨울철 저온"),
        Relation(subject="실리콘", predicate="aggravates", object="소음"),
    ]
    nodes = reifier.reify(concepts, rels)
    assert len(nodes) == 2, "두 기전 맥락은 노드 2개로 분리돼야 한다(바인딩 보존)"
    mechs = {str(n.mechanism) for n in nodes}
    assert mechs == {str(DOM.Rubber), str(DOM.Silicone)}, "기전이 한 노드로 섞이면 안 된다"
    # 노드 IRI 도 서로 달라야 한다(같은 노드에 병합 금지)
    assert len({n.iri for n in nodes}) == 2


# ── 6문장 재모델 일관성: seed + 컴파일된 Causation 이 OWL 일관 ────────────────────────────
def test_6문장_causation_시드_일관성() -> None:
    from rdflib import Graph

    from core.config import settings

    g = Graph()
    for name in ("m0.ttl", "m1_wiper.ttl", "m2_instances.ttl"):
        g.parse(settings.ontology_dir / name, format="turtle")
    for t in RuleCompiler().compile().causation:  # 파생 Causation 노드 합류
        g.add(t)
    assert disjoint_clashes(expand(g)) == [], "seed + Causation 이 배타 클래스 모순을 일으키면 안 된다"


def test_causation_shape_graph_는_손SHACL_아님() -> None:
    """shape 는 컴파일러 함수가 프로그램적으로 방출한다(shapes.ttl 손 편집 아님)."""
    g = causation_shape_graph()
    assert (DOM.CausationShape, RDF.type, None) in g
    # 세 역할이 모두 property shape 로 들어갔다
    paths = {str(g.value(p, SH.path)) for p in g.objects(DOM.CausationShape, SH.property)}
    assert paths == {str(EXT.manifestsSymptom), str(EXT.hasMechanism), str(EXT.underCondition)}
