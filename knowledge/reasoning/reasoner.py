"""OWL 추론 · 일관성 검사 — HermiT(owlready2) 우선, 없으면 owlrl 폴백.

이 개발기에는 JRE 가 없어 HermiT 가 뜨지 않는다. `/health` 의 `reasoner` 가 `no_jre` 로
정직하게 보고하고, 판정은 owlrl(OWL RL 의미론)로 계속 수행한다. Docker 이미지에는 JRE 를 넣는다(T-80).
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import owlrl
from rdflib import OWL, RDF, Graph, Namespace, URIRef

from core.config import settings
from schemas.errors import ReasonerError

log = logging.getLogger("knowledge.reasoner")

SPMM = Namespace("http://ex.org/spmm#")

#: M0 의 owl:AllDisjointClasses 를 코드로 옮긴 것. 상호 배타 집합.
DISJOINT_SETS: list[frozenset[URIRef]] = [
    frozenset({SPMM.Entity, SPMM.Form, SPMM.Behavior, SPMM.Attribute}),
    frozenset({SPMM.RequiredBehavior, SPMM.DesignedBehavior, SPMM.TestBehavior}),
]


@dataclass
class ConsistencyResult:
    consistent: bool
    clashes: list[str] = field(default_factory=list)
    engine: str = "owlrl"


def local(u: object) -> str:
    return str(u).split("#")[-1]


@lru_cache(maxsize=1)
def hermit_available() -> bool:
    """HermiT 는 Java 로 돈다. JRE 가 없으면 owlrl 로 폴백한다."""
    if shutil.which("java") is None:
        return False
    try:
        import owlready2  # noqa: F401
    except ImportError:
        return False
    return True


def reasoner_status() -> str:
    return "ok" if hermit_available() else "no_jre"


def expand(graph: Graph) -> Graph:
    """OWL RL 연역적 폐포. 원본을 건드리지 않는다."""
    inferred = Graph()
    for t in graph:
        inferred.add(t)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False, datatype_axioms=False).expand(inferred)
    return inferred


def disjoint_clashes(graph: Graph) -> list[str]:
    """한 개체가 상호 배타 클래스 둘 이상에 속하면 모순이다."""
    clashes: list[str] = []
    for subject in set(graph.subjects(RDF.type, None)):
        types = set(graph.objects(subject, RDF.type))
        for dset in DISJOINT_SETS:
            hit = types & dset
            if len(hit) >= 2:
                clashes.append(f"{local(subject)} 가 배타 클래스 {sorted(local(h) for h in hit)} 에 동시 소속")
    return clashes


class Reasoner:
    """`core.protocols.Reasoner` 구현."""

    def __init__(self, ontology_dir: Path | None = None) -> None:
        self._dir = ontology_dir or settings.ontology_dir

    def consistency(self, graph: Graph) -> ConsistencyResult:
        if hermit_available():
            try:
                return self._consistency_hermit(graph)
            except Exception as exc:  # pragma: no cover - JRE 있는 환경에서만
                log.warning("HermiT 실패, owlrl 로 폴백: %s", exc)

        try:
            inferred = expand(graph)
        except Exception as exc:
            raise ReasonerError(f"owlrl 추론 실패: {exc}") from exc

        clashes = disjoint_clashes(inferred)
        return ConsistencyResult(consistent=not clashes, clashes=clashes, engine="owlrl")

    def _consistency_hermit(self, graph: Graph) -> ConsistencyResult:  # pragma: no cover - JRE 필요
        import tempfile

        import owlready2

        with tempfile.NamedTemporaryFile(suffix=".owl", delete=False) as tmp:
            graph.serialize(destination=tmp.name, format="xml")
            world = owlready2.World()
            world.get_ontology(f"file://{tmp.name}").load()
            try:
                owlready2.sync_reasoner_hermit(world)
            except owlready2.OwlReadyInconsistentOntologyError as exc:
                # HermiT 는 '비일관' 판정만 주고 어떤 개체가 충돌했는지는 열거하지 않는다.
                # 보고를 owlrl 경로와 동일 포맷으로 맞추기 위해 결정론적 구조분석으로 충돌 개체를 열거한다.
                # (판정은 이미 HermiT 가 내렸다 — 여기선 진단 메시지만 보강. 구조분석이 못 짚으면 원문 유지.)
                clashes = disjoint_clashes(expand(graph)) or [str(exc)]
                return ConsistencyResult(consistent=False, clashes=clashes, engine="hermit")
        return ConsistencyResult(consistent=True, clashes=[], engine="hermit")

    def classify(self, iri: str, graph: Graph | None = None) -> list[str]:
        """개체의 추론된 타입 사슬 (WiperBlade ⊑ PartType ⊑ Artifact ⊑ Entity)."""
        g = graph if graph is not None else self._load_onto()
        inferred = expand(g)
        types = [
            o
            for o in inferred.objects(URIRef(iri), RDF.type)
            if isinstance(o, URIRef) and str(o).startswith("http://ex.org") and o != OWL.Class
        ]
        return sorted({local(t) for t in types})

    def _load_onto(self) -> Graph:
        g = Graph()
        for name in ("m0.ttl", "m1_wiper.ttl", "m2_instances.ttl"):
            g.parse(self._dir / name, format="turtle")
        return g
