"""T-93 — 저작(승인된 문장) → 구조화 규칙 파생 · 오버레이 영속.

포스트-g3 실 검증이 드러낸 구멍: **저작한 지식이 판정(satisfy)에 도달하지 않는다.**
규칙은 시드 `rules.ttl` 에서만 컴파일되고, `kg/save` 가 돌려주던 `derived` 는 영속되지 않는
일회용 투영이었다(게다가 증상을 프로젝트 카테고리로 오귀속했다 — 문장이 달라도 전부 `소음Rule`).

여기서 그 다리를 놓는다:
  추출(개념·관계) → **RuleSpec 파생**(조건·기전·증상·극성·카테고리) → 오버레이 TTL 영속
  → 컴파일러가 시드+오버레이를 함께 소비 → SHACL 게이트 → satisfy 판정에 반영.

파생은 **결정론**이다 — LLM 은 개념·관계까지만 만들고, 규칙 구조는 온톨로지 타입(T-94)이 정한다.
증상이 온톨로지에 없으면 규칙을 만들지 않는다(게이트가 될 수 없다) — 지식 문장은 저장되지만
판정에는 참여하지 않는다. **fail-closed 불변**: 접지되지 않은 것은 규칙이 되지 않는다.
"""
from __future__ import annotations

import logging
from pathlib import Path

from rdflib import RDF, RDFS, BNode, Graph, Literal, Namespace, URIRef

from core.config import settings
from reasoning.rules import Cond, RuleSpec, load_rules
from reasoning.spec_validate import SpecValidator
from schemas.models import Concept

log = logging.getLogger("knowledge.authoring")

DOM = Namespace("http://ex.org/domain#")

#: 추출 술어 → 규칙 극성.
_POLARITY = {"causes": "cause", "aggravates": "aggravate", "mitigates": "mitigate"}

#: 조건으로 쓸 수 있는 설계 경로 — 기전(재질)과 환경조건. 수치 조건은 문장에서 파생하지 않는다
#: (추출은 임계값을 만들지 않는다 — 임계는 규칙 편집·시드의 몫).
_MATERIAL_PATH = "hasMaterial"
_ENV_PATH = "operatesIn"


def derive_rule(
    *,
    sentence_code: str,
    sentence_text: str,
    category: str,
    concepts: list[Concept],
    relations: list,
    validator: SpecValidator,
) -> RuleSpec | None:
    """승인된 문장의 추출 결과 → 구조화 규칙 하나. 만들 수 없으면 None.

    조건: (1) 증상이 온톨로지 Symptom 으로 접지되고, (2) 조건(기전 재질 / 환경)이 하나 이상 있어야 한다.
    조건이 없으면 "모든 설계가 이 증상을 낸다"는 뜻이 되어 과차단이다 → 규칙을 만들지 않는다.
    """
    def iri_of(label: str) -> URIRef | None:
        found = validator.iri_for(label)
        return URIRef(found) if found else None

    def is_type(label: str, expected: str) -> bool:
        return validator.canonical_type(label) == expected

    # (1) 증상·극성 — 접지된 Symptom 을 대상으로 하는 인과 관계에서만.
    symptom_label = polarity = None
    for rel in relations:
        if rel.predicate in _POLARITY and is_type(rel.object, "Symptom"):
            symptom_label, polarity = rel.object, _POLARITY[rel.predicate]
            break
    if symptom_label is None or polarity is None:
        log.info("규칙 파생 없음(%s) — 접지된 증상이 없다", sentence_code)
        return None

    symptom_iri = iri_of(symptom_label)
    if symptom_iri is None:  # pragma: no cover — is_type 이 이미 보장
        return None

    # (2) 조건 — 기전(재질) · 환경(증상 앵커 conditionedOn).
    conds: list[Cond] = []
    material = _material_iri(relations, symptom_label, iri_of, is_type)
    if material is not None:
        conds.append(Cond(path=_MATERIAL_PATH, op="eq", val=material))
    for rel in relations:
        if rel.predicate != "conditionedOn" or rel.subject != symptom_label:
            continue
        if not is_type(rel.object, "EnvCondition"):
            # **fail-closed**: 문장이 조건을 말하는데 그 조건이 접지되지 않았다. 조건을 빼고 규칙을 만들면
            # 문장보다 **넓은** 규칙("모든 고무 → 균열")이 되어, 없는 지식을 지어내는 것과 같다.
            # 조건을 온톨로지에 편입(거버넌스)한 뒤에 규칙이 된다.
            log.info("규칙 파생 없음(%s) — 조건 %r 이 접지되지 않았다(EnvCondition 아님)", sentence_code, rel.object)
            return None
        env = iri_of(rel.object)
        if env is not None and not any(c.path == _ENV_PATH for c in conds):
            conds.append(Cond(path=_ENV_PATH, op="eq", val=env))

    if not conds:
        log.info("규칙 파생 없음(%s) — 조건(재질·환경)이 없다 → 과차단 방지", sentence_code)
        return None

    return RuleSpec(
        id=f"{sentence_code}Rule",  # 문장별 고유 — 예전엔 카테고리명(소음Rule)이라 문장끼리 충돌했다
        label=sentence_text.strip(),
        category=category,
        polarity=polarity,
        basis=sentence_code,
        symptom=str(symptom_iri).split("#")[-1],
        conds=tuple(conds),
        from_sentences=(sentence_code,),
    )


def find_equivalent(rule: RuleSpec, existing: list[RuleSpec]) -> RuleSpec | None:
    """이미 같은 규칙이 있으면 그것을 돌려준다 — **같은 사실을 다시 말해도 규칙은 하나다.**

    (증상·극성·조건집합)이 같으면 등가다. 없으면 게이트가 둘로 늘어 같은 위반이 두 번 잡히고,
    시드와 등가인 문장을 저작하는 순간 시드 회귀가 깨진다.
    """
    key = _equiv_key(rule)
    return next((r for r in existing if _equiv_key(r) == key), None)


def _equiv_key(rule: RuleSpec) -> tuple:
    conds = sorted((c.path, c.op, str(c.val), tuple(c.ref_list)) for c in rule.conds)
    return (rule.symptom, rule.polarity, tuple(conds))


def _material_iri(relations: list, symptom_label: str, iri_of, is_type) -> URIRef | None:  # noqa: ANN001
    """기전이 되는 재질. (a) 재질이 직접 증상을 유발하거나, (b) 부품의 hasMaterial 이 재질일 때."""
    for rel in relations:
        if rel.predicate in _POLARITY and rel.object == symptom_label and is_type(rel.subject, "Material"):
            return iri_of(rel.subject)
    for rel in relations:
        if rel.predicate == "hasMaterial" and is_type(rel.object, "Material"):
            return iri_of(rel.object)
    return None


def rule_to_graph(rule: RuleSpec) -> Graph:
    """RuleSpec → rules.ttl 어휘(dom:DesignRule). 오버레이도 시드와 **같은 형식**이다(단일 진실원)."""
    g = Graph()
    g.bind("dom", DOM)
    node = DOM[rule.id]
    g.add((node, RDF.type, DOM.DesignRule))
    g.add((node, RDFS.label, Literal(rule.label)))
    g.add((node, DOM.category, Literal(rule.category)))
    g.add((node, DOM.polarity, Literal(rule.polarity)))
    g.add((node, DOM.basis, Literal(rule.basis)))
    g.add((node, DOM.aboutSymptom, DOM[rule.symptom] if "#" not in rule.symptom else URIRef(rule.symptom)))
    for code in rule.from_sentences:
        g.add((node, DOM.fromSentence, DOM[code]))
    for cond in rule.conds:
        c = BNode()
        g.add((node, DOM.hasCond, c))
        g.add((c, DOM.onPath, DOM[cond.path]))
        g.add((c, DOM.op, Literal(cond.op)))
        if cond.val is not None:
            g.add((c, DOM.val, cond.val))
    return g


class AuthoringRuleStore:
    """저작 파생 규칙의 오버레이 TTL — T-85 상위 온톨로지 오버레이와 같은 패턴(승인분만 영속).

    시드 `rules.ttl` 은 읽기 전용이다. 저작분은 여기에 쌓이고, 컴파일러가 둘을 함께 읽는다.
    비어 있으면(파일 없음) 시드와 **완전히 동일한 컴파일 결과** → 시드 회귀 불변.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.authoring_rules_path

    def load(self) -> Graph:
        g = Graph()
        if self.path.exists():
            g.parse(self.path, format="turtle")
        return g

    def rules(self) -> list[RuleSpec]:
        return load_rules(self.path) if self.path.exists() else []

    def upsert(self, rule: RuleSpec) -> None:
        """같은 규칙 id 는 덮어쓴다(문장 재저장·수정 시 규칙이 중복되지 않게)."""
        g = self.load()
        self._remove(g, rule.id)
        for triple in rule_to_graph(rule):
            g.add(triple)
        self._write(g)

    def remove(self, rule_id: str) -> None:
        """보상 롤백용 — 저장이 뒤에서 실패하면 규칙도 되돌린다."""
        if not self.path.exists():
            return
        g = self.load()
        self._remove(g, rule_id)
        self._write(g)

    @staticmethod
    def _remove(g: Graph, rule_id: str) -> None:
        node = DOM[rule_id]
        for cond in list(g.objects(node, DOM.hasCond)):
            g.remove((cond, None, None))
        g.remove((node, None, None))

    def _write(self, g: Graph) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        g.serialize(destination=self.path, format="turtle")
