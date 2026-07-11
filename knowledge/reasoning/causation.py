"""T-91 — 조건부 인과의 reification (W3C n-ary) : 저작(추출) 프레임의 Causation 표현·검증.

이항 트리플 (X causes S)+(S conditionedOn C) 우회는 (a) 바인딩을 잃고, (b) 추출이 조건의 주어를
부품(PartType)으로 틀리면 `conditionedOn` 도메인(FailureBehavior) 위반이 난다.
여기서는 (기전·조건·증상)을 **한 Causation 노드**로 묶어 두 문제를 모두 없앤다.

- `reify_relations` : 추출 개념·관계(플랫 트리플)에서 인과 프레임을 감지해 Causation 노드로 재화.
- `validate_causation` : Causation 구조를 **컴파일러가 방출한 CausationShape**(손 SHACL 아님)로 검증.

접지(가드레일)는 fail-closed 불변 — 검증 실패/불명은 위반으로 처리한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pyshacl
from rdflib import RDF, Graph, Literal, Namespace, URIRef

from core.config import settings
from reasoning.compiler import causation_shape_graph
from reasoning.spec_validate import SpecValidator
from schemas.models import Concept, Violation

log = logging.getLogger("knowledge.causation")

DOM = Namespace("http://ex.org/domain#")
EXT = Namespace("http://ex.org/spmm-ext#")
SH = Namespace("http://www.w3.org/ns/shacl#")

#: 인과 프레임을 이루는 술어. 조건은 **증상 앵커**(S conditionedOn C)로만 받는다 —
#: 부품 앵커(블레이드 conditionedOn 겨울)는 애초에 프레임이 아니다(그게 이슈2b 였다).
_CAUSE_PREDS = {"causes", "aggravates"}
_MITIGATE_PREDS = {"mitigates"}


@dataclass
class CausationNode:
    """재화된 인과 하나. (기전·조건·증상)을 묶는다 — 바인딩 보존."""

    iri: URIRef
    mechanism: URIRef | None
    condition: URIRef | None
    symptom: URIRef | None
    polarity: str


class CausationReifier:
    """추출 개념·관계 → Causation 노드. 라벨→IRI 는 도메인 어휘층(SpecValidator)으로 해석한다."""

    def __init__(self, validator: SpecValidator | None = None, ontology_dir: Path | None = None) -> None:
        self._dir = ontology_dir or settings.ontology_dir
        self.validator = validator or SpecValidator(self._dir)
        # 타입 판정용 온톨로지(m0+m1+lexicon+overlay 는 validator 가 이미 로드) — 검증 데이터 그래프에 합류.
        self._onto = self.validator._onto  # noqa: SLF001 — 같은 패키지, 읽기전용 공유

    def _iri(self, label: str) -> URIRef | None:
        found = self.validator.iri_for(label)
        return URIRef(found) if found else None

    def reify(self, concepts: list[Concept], relations: list) -> list[CausationNode]:
        """인과 프레임 감지 → Causation 노드. 한 증상에 (기전,조건) 맥락이 여럿이면 노드도 여럿(바인딩 보존).

        패턴: (mechanism causes/aggravates symptom) 를 축으로, 같은 증상에 붙은
        (symptom conditionedOn condition) 을 조건으로 결합한다. 재질(hasMaterial)은 기전의 부속.
        """
        # 증상 → 붙은 조건들(증상 앵커 conditionedOn 만 인정 — 부품 앵커는 프레임이 아니다).
        cond_by_symptom: dict[str, list[str]] = {}
        for r in relations:
            if r.predicate == "conditionedOn":
                cond_by_symptom.setdefault(r.subject, []).append(r.object)

        nodes: list[CausationNode] = []
        seen: set[tuple[str, str | None, str | None, str]] = set()
        for r in relations:
            if r.predicate not in (_CAUSE_PREDS | _MITIGATE_PREDS):
                continue
            mech_label, sym_label = r.subject, r.object
            polarity = "mitigate" if r.predicate in _MITIGATE_PREDS else (
                "aggravate" if r.predicate == "aggravates" else "cause"
            )
            conds = cond_by_symptom.get(sym_label) or [None]  # 조건 없으면 무조건 인과 하나
            for cond_label in conds:
                key = (mech_label, cond_label, sym_label, polarity)
                if key in seen:
                    continue
                seen.add(key)
                idx = len(nodes) + 1
                nodes.append(
                    CausationNode(
                        iri=DOM[f"_authored_causation_{idx}"],
                        mechanism=self._iri(mech_label),
                        condition=self._iri(cond_label) if cond_label else None,
                        symptom=self._iri(sym_label),
                        polarity=polarity,
                    )
                )
        return nodes

    def to_graph(self, nodes: list[CausationNode]) -> Graph:
        g = Graph()
        for n in nodes:
            g.add((n.iri, RDF.type, EXT.Causation))
            if n.mechanism is not None:
                g.add((n.iri, EXT.hasMechanism, n.mechanism))
            if n.condition is not None:
                g.add((n.iri, EXT.underCondition, n.condition))
            if n.symptom is not None:
                g.add((n.iri, EXT.manifestsSymptom, n.symptom))
            g.add((n.iri, EXT.causationPolarity, Literal(n.polarity)))
        return g

    def validate(self, nodes: list[CausationNode]) -> list[Violation]:
        """Causation 구조를 CausationShape 로 검증한다. fail-closed: 검증 예외도 위반으로 본다."""
        if not nodes:
            return []
        data = Graph()
        for t in self._onto:  # 타입 트리플(Winter a EnvCondition · Noise a Symptom …) 이 sh:class 에 필요
            data.add(t)
        for t in self.to_graph(nodes):
            data.add(t)
        try:
            _conforms, report, _text = pyshacl.validate(
                data_graph=data,
                shacl_graph=causation_shape_graph(),
                ont_graph=None,
                inference="none",
                advanced=True,
                meta_shacl=False,
            )
        except Exception as exc:  # noqa: BLE001 — fail-closed
            log.warning("Causation 검증 실패(fail-closed): %s", exc)
            return [Violation(code="shacl_constraint", severity="violation", offender="Causation",
                              message="Causation 구조 검증에 실패했습니다.", source_shape="CausationShape")]

        violations: list[Violation] = []
        for result in report.subjects(RDF.type, SH.ValidationResult):
            focus = report.value(result, SH.focusNode)
            msg = report.value(result, SH.resultMessage)
            violations.append(Violation(
                code="shacl_constraint", severity="violation",
                offender=str(focus).split("#")[-1] if focus else "Causation",
                message=str(msg) if msg else "Causation 구조 위반",
                source_shape="CausationShape",
            ))
        return violations


@lru_cache(maxsize=1)
def get_reifier() -> CausationReifier:
    return CausationReifier()
