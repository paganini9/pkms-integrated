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
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

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


# (T-89) 하드코딩 도메인 어휘는 온톨로지 `lexicon.ttl` 의 skos:altLabel 로 이관됐다.
# 소속 판정(concept_in_domain)은 prefLabel(rdfs:label) + altLabel 을 함께 읽는다.


class SpecValidator:
    """M0 클래스 계층을 미리 펼쳐 두고, 개념 타입이 제약을 만족하는지 확인한다.

    owlrl 전체 폐포는 느리다 — `rdfs:subClassOf` 만 전이 폐포로 계산하면 충분하고 결정론적이다.
    """

    def __init__(self, ontology_dir: Path | None = None) -> None:
        self._dir = ontology_dir or settings.ontology_dir
        self._onto = Graph()
        for name in ("m0.ttl", "m1_wiper.ttl", "lexicon.ttl"):
            path = self._dir / name
            if path.exists():
                self._onto.parse(path, format="turtle")
        # 어휘층(T-89): prefLabel(rdfs:label) + altLabel(skos:altLabel) 을 소속 어휘로 색인.
        self._label_to_iri: dict[str, URIRef] = {}
        for subject, label in self._onto.subject_objects(RDFS.label):
            if isinstance(subject, URIRef):
                self._index_label(subject, str(label))
        for subject, label in self._onto.subject_objects(SKOS.altLabel):
            if isinstance(subject, URIRef):
                self._label_to_iri.setdefault(str(label).strip(), subject)

    def _index_label(self, subject: URIRef, text: str) -> None:
        """'Rubber (고무)' → 'Rubber' 와 '고무' 둘 다 색인. 일반 라벨은 그대로."""
        self._label_to_iri.setdefault(text.split("(")[0].strip(), subject)
        if "(" in text and ")" in text:
            self._label_to_iri.setdefault(text[text.index("(") + 1 : text.rindex(")")].strip(), subject)

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
        if found is None:
            found = self._label_to_iri.get(label.strip())
        return str(found) if found else None

    def concept_in_domain(self, label: str) -> bool:
        """라벨이 도메인(와이퍼) 온톨로지의 개념/클래스로 해석되는가 — 결정론적 소속 판정(T-73).

        접지(가드레일)의 단일 진실원. LLM 추출 규율이 아니라 이 판정이 도메인 경계를 정한다.
        온톨로지 어휘층(prefLabel + skos:altLabel) **정확일치**만 인정한다. 부분일치는 쓰지 않는다
        ("타이어 고무"는 어떤 라벨과도 정확일치 안 하므로 여전히 차단 = 우회 방어).
        """
        return self.iri_for(label) is not None

    def validate(self, concepts: list[Concept], relations: list) -> list[Violation]:
        violations: list[Violation] = []
        by_label: dict[str, Concept] = {}

        # disjoint — 같은 라벨이 배타 범주 둘에 배정됐는가
        seen_types: dict[str, set[ConceptType]] = {}
        for concept in concepts:
            seen_types.setdefault(concept.label, set()).add(concept.type)
            by_label[concept.label] = concept

        # T-73 (CD-7 "범주 밖 개념") — 추출 개념이 **도메인 온톨로지에 없으면** unknown_concept.
        # 목적: 접지(가드레일)를 LLM 추출 규율이 아니라 **결정론적 온톨로지 소속**으로 판정하게 한다.
        # (D8: 예전엔 관계가 개념목록을 자기참조하는지만 봤다 → 온톨로지 소속을 전혀 안 봤다.)
        # severity=warning: 저장은 막지 않되(관계 드롭·HITL 검토), QA 접지는 이 offender 로 계층 판정.
        for label in seen_types:  # 라벨 단위(중복 제거)
            if self.concept_in_domain(label):
                continue
            violations.append(
                Violation(
                    code="unknown_concept",
                    severity="warning",
                    offender=label,
                    message=f"'{label}' 은(는) 도메인(와이퍼) 온톨로지에 없는 개념(범주 밖)입니다.",
                )
            )

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
