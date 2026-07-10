"""명세 검증 — 추출된 개념·관계가 M0/M0-ext 온톨로지를 위반하는가 (FR-02).

LLM 이 뽑은 초안을 **결정론적으로** 거르는 게이트다. 위반 = 환각 후보.
  · `causes_range`   — `causes/mitigates/aggravates` 의 대상은 증상(FailureBehavior)이어야 한다
  · `disjoint`       — 한 개념이 상호 배타 범주(Entity/Form/Behavior/Attribute) 둘에 속할 수 없다
  · `unknown_concept`— 관계가 개념 목록에 없는 대상을 가리킨다

CD-7: `severity="violation"` 이면 UI amber + 저장 차단. `warning` 이면 정보 표시 + 저장 허용.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from rdflib import RDFS, Graph, Namespace, URIRef

from core.config import settings
from schemas.models import Concept, ConceptType, Predicate, Violation

SPMM = Namespace("http://ex.org/spmm#")
EXT = Namespace("http://ex.org/spmm-ext#")
DOM = Namespace("http://ex.org/domain#")

#: 추출 스키마의 개념 타입 → M0 클래스 IRI
TYPE_TO_CLASS: dict[str, URIRef] = {
    "PartType": EXT.PartType,
    "Component": EXT.Component,
    "Material": SPMM.Material,
    "VehicleType": EXT.VehicleType,
    "EnvCondition": EXT.EnvCondition,
    "Symptom": EXT.Symptom,
    "Behavior": SPMM.Behavior,
    "Attribute": SPMM.Attribute,
}

#: 술어 → (domain 제약, range 제약). None 이면 제약 없음.
PREDICATE_CONSTRAINTS: dict[str, tuple[URIRef | None, URIRef | None]] = {
    "causes": (None, EXT.FailureBehavior),
    "mitigates": (None, EXT.FailureBehavior),
    "aggravates": (None, EXT.FailureBehavior),
    "conditionedOn": (EXT.FailureBehavior, EXT.EnvCondition),
    "hasMaterial": (EXT.PartType, SPMM.Material),
    "mountedOn": (None, EXT.VehicleType),
    "operatesIn": (None, EXT.EnvCondition),
    "has_part": (None, None),
}

#: M0 의 owl:AllDisjointClasses
DISJOINT_SETS: list[frozenset[URIRef]] = [
    frozenset({SPMM.Entity, SPMM.Form, SPMM.Behavior, SPMM.Attribute}),
    frozenset({SPMM.RequiredBehavior, SPMM.DesignedBehavior, SPMM.TestBehavior}),
]

_PREDICATE_KO = {
    "causes": "유발(causes)",
    "mitigates": "해소(mitigates)",
    "aggravates": "악화(aggravates)",
    "conditionedOn": "조건(conditionedOn)",
    "hasMaterial": "재질(hasMaterial)",
    "mountedOn": "장착(mountedOn)",
    "operatesIn": "운용환경(operatesIn)",
}


def local(u: object) -> str:
    return str(u).split("#")[-1]


class SpecValidator:
    """M0 클래스 계층을 미리 펼쳐 두고, 개념 타입이 제약을 만족하는지 확인한다.

    owlrl 전체 폐포는 느리다 — `rdfs:subClassOf` 만 전이 폐포로 계산하면 충분하고 결정론적이다.
    """

    def __init__(self, ontology_dir: Path | None = None) -> None:
        self._dir = ontology_dir or settings.ontology_dir
        self._onto = Graph()
        for name in ("m0.ttl", "m1_wiper.ttl"):
            self._onto.parse(self._dir / name, format="turtle")
        self._label_to_iri = {
            str(label).split("(")[0].strip(): subject
            for subject, label in self._onto.subject_objects(RDFS.label)
        }
        # 한글 라벨도 찾을 수 있게: "Rubber (고무)" → "고무"
        for subject, label in self._onto.subject_objects(RDFS.label):
            text = str(label)
            if "(" in text and ")" in text:
                korean = text[text.index("(") + 1 : text.rindex(")")].strip()
                self._label_to_iri.setdefault(korean, subject)

    @lru_cache(maxsize=256)  # noqa: B019
    def _ancestors(self, cls: URIRef) -> frozenset[URIRef]:
        """cls 와 그 모든 상위 클래스 (rdfs:subClassOf 전이 폐포)."""
        seen: set[URIRef] = set()
        stack = [cls]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            for parent in self._onto.objects(current, RDFS.subClassOf):
                if isinstance(parent, URIRef):
                    stack.append(parent)
        return frozenset(seen)

    def _satisfies(self, concept_type: ConceptType, constraint: URIRef) -> bool:
        cls = TYPE_TO_CLASS.get(concept_type)
        return cls is not None and constraint in self._ancestors(cls)

    def iri_for(self, label: str) -> str | None:
        found = self._label_to_iri.get(label)
        return str(found) if found else None

    def validate(self, concepts: list[Concept], relations: list) -> list[Violation]:
        violations: list[Violation] = []
        by_label: dict[str, Concept] = {}

        # disjoint — 같은 라벨이 배타 범주 둘에 배정됐는가
        seen_types: dict[str, set[ConceptType]] = {}
        for concept in concepts:
            seen_types.setdefault(concept.label, set()).add(concept.type)
            by_label[concept.label] = concept

        for label, types in seen_types.items():
            if len(types) < 2:
                continue
            tops = {t for ct in types for t in self._ancestors(TYPE_TO_CLASS[ct])}
            for dset in DISJOINT_SETS:
                hit = tops & dset
                if len(hit) >= 2:
                    violations.append(
                        Violation(
                            code="disjoint",
                            severity="violation",
                            offender=label,
                            offender_iri=self.iri_for(label),
                            message=(
                                f"'{label}' 이(가) 상호 배타 범주 {sorted(local(h) for h in hit)} 에 동시에 배정되었습니다. "
                                f"하나의 범주만 선택해 주세요."
                            ),
                            source_shape="DisjointShape",
                        )
                    )

        for relation in relations:
            domain_c, range_c = PREDICATE_CONSTRAINTS.get(relation.predicate, (None, None))
            predicate_ko = _PREDICATE_KO.get(relation.predicate, relation.predicate)

            for role, label, constraint in (
                ("주어", relation.subject, domain_c),
                ("대상", relation.object, range_c),
            ):
                concept = by_label.get(label)
                if concept is None:
                    violations.append(
                        Violation(
                            code="unknown_concept",
                            severity="warning",  # CD-7: 저장은 허용하되 해당 관계는 드롭
                            offender=label,
                            message=f"관계의 {role} '{label}' 이(가) 추출된 개념 목록에 없습니다. 이 관계는 저장되지 않습니다.",
                        )
                    )
                    continue
                if constraint is None or self._satisfies(concept.type, constraint):
                    continue

                code = "causes_range" if relation.predicate in {"causes", "mitigates", "aggravates"} and role == "대상" else "shacl_constraint"
                expected = "증상(Symptom)" if constraint == EXT.FailureBehavior else f"{local(constraint)}"
                violations.append(
                    Violation(
                        code=code,
                        severity="violation",  # CD-7: amber + 저장 차단
                        offender=label,
                        offender_iri=self.iri_for(label),
                        message=(
                            f"'{predicate_ko}'의 {role}은(는) {expected}이어야 하는데 "
                            f"'{label}'은(는) {concept.type}입니다."
                        ),
                        source_shape=f"{relation.predicate.capitalize()}RangeShape"
                        if role == "대상"
                        else f"{relation.predicate.capitalize()}DomainShape",
                    )
                )

        return violations


@lru_cache(maxsize=1)
def get_validator() -> SpecValidator:
    return SpecValidator()
