"""T-80 — HermiT 경로 스모크 + owlrl↔HermiT 패리티.

호스트엔 JRE 가 없어(no_jre) 이 경로는 한 번도 실행된 적이 없다(`_consistency_hermit`=no cover).
Docker(temurin JRE) 안에서 처음으로 실행·검증한다. JRE 없으면 skip.

- 스모크: seed 는 HermiT 로 **일관**, 고의 모순(배타 클래스 동시소속)은 HermiT 가 **inconsistent** 로 잡는다.
- 패리티: owlrl(dev)과 HermiT(prod)가 seed 일관성·모순 검출에 **동의**한다.
  (OWL RL 은 불완전 — 불일치 시 prod 서프라이즈. seed 규모에선 일치해야 한다.)
"""
from __future__ import annotations

import pytest
from rdflib import RDF, Graph, Namespace, URIRef

from core.config import settings
from reasoning.reasoner import Reasoner, disjoint_clashes, expand, hermit_available

SPMM = Namespace("http://ex.org/spmm#")
DOM = Namespace("http://ex.org/domain#")

requires_jre = pytest.mark.skipif(
    not hermit_available(), reason="JRE 없음 — HermiT 미가용(Docker 컨테이너에서 실행)"
)


def _seed_graph() -> Graph:
    g = Graph()
    for name in ("m0.ttl", "m1_wiper.ttl", "m2_instances.ttl"):
        g.parse(settings.ontology_dir / name, format="turtle")
    return g


def _contradiction_graph() -> Graph:
    """seed + 배타 클래스(Entity ⊥ Behavior) 동시소속 개체 → OWL 비일관."""
    g = _seed_graph()
    clash = URIRef(f"{DOM}TestClash")
    g.add((clash, RDF.type, SPMM.Entity))
    g.add((clash, RDF.type, SPMM.Behavior))
    return g


# ── 스모크 (미검증 경로 첫 실행) ──────────────────────────────────────────────
@requires_jre
def test_hermit_seed_is_consistent() -> None:
    res = Reasoner().consistency(_seed_graph())
    assert res.engine == "hermit"
    assert res.consistent is True
    assert res.clashes == []


@requires_jre
def test_hermit_detects_intentional_contradiction() -> None:
    res = Reasoner().consistency(_contradiction_graph())
    assert res.engine == "hermit"
    assert res.consistent is False
    assert res.clashes, "HermiT 가 모순을 클래시로 보고하지 않았다"


# ── 패리티 (owlrl ↔ HermiT) ──────────────────────────────────────────────────
@requires_jre
def test_owlrl_hermit_parity_on_seed() -> None:
    seed = _seed_graph()
    owlrl_consistent = len(disjoint_clashes(expand(seed))) == 0
    hermit = Reasoner().consistency(seed)
    assert owlrl_consistent is True
    assert hermit.consistent == owlrl_consistent, "seed 일관성 판정이 두 리즈너에서 갈렸다"


@requires_jre
def test_owlrl_hermit_parity_on_contradiction() -> None:
    g = _contradiction_graph()
    owlrl_consistent = len(disjoint_clashes(expand(g))) == 0
    hermit = Reasoner().consistency(g)
    assert owlrl_consistent is False, "owlrl 이 고의 모순을 못 잡았다"
    assert hermit.consistent is False, "HermiT 가 고의 모순을 못 잡았다"
    # 두 리즈너가 '비일관'에 동의(패리티).


def test_owlrl_baseline_runs_without_jre() -> None:
    """JRE 유무와 무관하게 owlrl 경로는 항상 동작한다(회귀 안전망)."""
    seed = _seed_graph()
    assert disjoint_clashes(expand(seed)) == []
    assert len(disjoint_clashes(expand(_contradiction_graph()))) > 0
