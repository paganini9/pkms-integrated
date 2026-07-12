"""규칙 컴파일러 — 구조화 DesignRule → SHACL 게이트 · 인과엣지 · 사람용 뷰.

`ontology-ref/gen_shacl.py` 이식. 단일 진실원은 `rules.ttl`, 나머지는 전부 파생물이다.
**CD-4**: 프로젝트 지식범위(카테고리) 필터는 **컴파일 시점**에 적용한다.
판정 후 필터링(post-filter)을 하면 게이트 수가 달라져 결과가 틀린다.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rdflib import RDF, BNode, Graph, Literal, Namespace, URIRef

from core.config import settings
from reasoning.rules import Cond, RuleSpec, load_rules, load_sentence_polarity, loc, sentence_sort_key

DOM = Namespace("http://ex.org/domain#")
EXT = Namespace("http://ex.org/spmm-ext#")
SH = Namespace("http://www.w3.org/ns/shacl#")

POLARITY_PREDICATE = {"cause": "causes", "mitigate": "mitigates", "aggravate": "aggravates"}


@dataclass(frozen=True)
class Gate:
    """컴파일된 SHACL NodeShape 하나. 위반 시 어떤 증상·어떤 문장 근거인지 되짚는다."""

    shape_id: str
    rule_id: str
    symptom: str
    basis: str
    polarity: str
    category: str
    message: str


@dataclass
class CompiledRules:
    shapes: Graph
    causal: Graph
    human_view: list[str]
    gates: dict[str, Gate]  # shape_id → Gate
    applied_rules: list[RuleSpec]
    applied_categories: list[str]
    shapes_hash: str = ""
    #: T-91 — 규칙에서 파생한 reified 인과 노드(개체 데이터). 지식표현·바인딩 보존·질의용.
    #: 설계-satisfy 경로(shapes/gates)와 무관하다 — satisfy 는 이 그래프를 보지 않는다.
    causation: Graph = field(default_factory=Graph)
    #: T-91 — Causation 구조 SHACL(세 역할 타입·필수). 저작(추출) 검증에 쓴다. 손 SHACL 아님(컴파일러 방출).
    causation_shape: Graph = field(default_factory=Graph)
    """컴파일 시점에 **한 번** 계산해 고정한다.

    매번 다시 계산하면 안 된다 — pySHACL 이 검증 중 shapes 그래프에 트리플을 주입하기 때문에
    호출할 때마다 해시가 달라지고, satisfy 시그니처 캐시가 영원히 빗나간다.
    """

    def shapes_copy(self) -> Graph:
        """pySHACL 에 넘길 사본. 정본을 넘기면 pySHACL 이 그것을 변형한다."""
        copy = Graph()
        for prefix, namespace in self.shapes.namespaces():
            copy.bind(prefix, namespace)
        for triple in self.shapes:
            copy.add(triple)
        return copy

    @property
    def rule_ids(self) -> set[str]:
        """프로젝트 지식범위로 **컴파일된** 규칙 id 집합 (mitigate 포함).

        CD-9: 03 RAG 의 `verified` 판정 근거. `gate_rules` 를 쓰면 mitigate 규칙(SiliconeRule)이
        미검증으로 떨어져, AC-2 가 설계 B 의 근거로 요구하는 S2·S5 를 인용할 수 없게 된다.
        """
        return {r.id for r in self.applied_rules}

    @property
    def gate_rules(self) -> set[str]:
        """SHACL 게이트로 컴파일된 규칙 id 집합.

        03 RAG 의 `CompiledRuleVerifier` 가 "이 문장의 규칙이 실제로 검증 게이트가 되었는가"를
        판정하는 근거다. `mitigate` 규칙은 게이트를 만들지 않으므로 여기 없다.
        """
        return {g.rule_id for g in self.gates.values()}

    @property
    def gate_sentences(self) -> set[str]:
        """게이트의 근거 문장 코드 집합 (basis 를 콤마 분해)."""
        return {code for g in self.gates.values() for code in g.basis.split(",")}


def _iri(u: object) -> str:
    return f"<{u}>"


def cond_to_sparql(cond: Cond) -> str:
    """조건 → SHACL sh:select 의 WHERE 절 조각. (gen_shacl.cond_to_sparql 이식)"""
    path = DOM[cond.path]
    if cond.op == "eq":
        if isinstance(cond.val, URIRef):
            return f"$this {_iri(path)} {_iri(cond.val)} ."
        return f'$this {_iri(path)} ?{cond.path} . FILTER(str(?{cond.path}) = "{cond.val}")'
    if cond.op in ("lt", "le", "gt", "ge"):
        sym = {"lt": "<", "le": "<=", "gt": ">", "ge": ">="}[cond.op]
        return f"$this {_iri(path)} ?{cond.path} . FILTER(?{cond.path} {sym} {cond.val})"
    if cond.op == "gtPath":
        p1, p2 = cond.ref_list
        return f"$this {_iri(path)} ?a . $this {_iri(DOM[p1])} ?x . ?x {_iri(DOM[p2])} ?b . FILTER(?a > ?b)"
    raise ValueError(f"알 수 없는 연산자: {cond.op}")


def _rule_mechanism(rule: RuleSpec) -> URIRef:
    """규칙의 기전(mechanism) 개념. 재질 eq 조건이 있으면 그 재질, 없으면 설계 주체(WiperBlade).

    (수치 규칙 S3 길이·S4 압력·S6 형상은 재질이 없으니 블레이드를 기전으로 — 임계 판정은
     설계-satisfy 경로가 그대로 담당한다. 여기 Causation 노드는 지식표현·바인딩용이다.)
    """
    for c in rule.conds:
        if c.path == "hasMaterial" and isinstance(c.val, URIRef):
            return c.val
    return DOM.WiperBlade


def _rule_condition(rule: RuleSpec) -> URIRef | None:
    """규칙의 환경 조건(EnvCondition). operatesIn eq 조건이 있을 때만(예: S1 겨울)."""
    for c in rule.conds:
        if c.path == "operatesIn" and isinstance(c.val, URIRef):
            return c.val
    return None


def causation_shape_graph() -> Graph:
    """Causation 구조 SHACL — 세 역할의 필수·타입 제약. 저작(추출) 검증의 단일 진실원(손 SHACL 아님).

    - manifestsSymptom: 필수(≥1) · 대상은 Symptom
    - hasMechanism:     필수(≥1)
    - underCondition:   선택 · 있으면 대상은 EnvCondition
    """
    g = Graph()
    g.bind("sh", SH)
    g.bind("ext", EXT)
    g.bind("dom", DOM)
    shape = DOM.CausationShape
    g.add((shape, RDF.type, SH.NodeShape))
    g.add((shape, SH.targetClass, EXT.Causation))
    specs = [
        (EXT.manifestsSymptom, 1, EXT.Symptom, "Causation 은 manifestsSymptom(증상)을 하나 이상 가져야 하고 대상은 Symptom 이어야 합니다."),
        (EXT.hasMechanism, 1, None, "Causation 은 hasMechanism(기전)을 하나 이상 가져야 합니다."),
        (EXT.underCondition, 0, EXT.EnvCondition, "underCondition(조건)의 대상은 EnvCondition 이어야 합니다."),
    ]
    for path, min_count, cls, msg in specs:
        p = BNode()
        g.add((shape, SH.property, p))
        g.add((p, SH.path, path))
        if min_count:
            g.add((p, SH.minCount, Literal(min_count)))
        if cls is not None:
            g.add((p, SH["class"], cls))
        g.add((p, SH.message, Literal(msg)))
        g.add((p, SH.severity, SH.Violation))
    return g


def compile_rules(rules: list[RuleSpec], categories: set[str] | None = None) -> CompiledRules:
    """categories=None 이면 전체. 아니면 해당 카테고리 규칙만 (CD-4)."""
    shapes = Graph()
    shapes.bind("sh", SH)
    shapes.bind("dom", DOM)
    causal = Graph()
    causal.bind("ext", EXT)
    causation = Graph()
    causation.bind("ext", EXT)
    causation.bind("dom", DOM)
    human: list[str] = []
    gates: dict[str, Gate] = {}
    applied: list[RuleSpec] = []

    for rule in sorted(rules, key=lambda r: r.id):
        if categories is not None and rule.category not in categories:
            continue
        applied.append(rule)
        human.append(f"{rule.label}  [{rule.polarity}·{rule.basis}·{rule.category}] → {rule.symptom}")
        causal.add((DOM[rule.id], EXT[POLARITY_PREDICATE[rule.polarity]], DOM[rule.symptom]))

        # T-91 — reified 인과 노드(규칙당 하나). (기전·조건·증상)을 한 노드로 묶어 바인딩을 보존한다.
        # 이항 (X causes S)+(S conditionedOn C) 과 달리 주어=Causation 이라 PartType-conditionedOn 위반이 없다.
        node = DOM[f"Causation_{rule.id}"]
        causation.add((node, RDF.type, EXT.Causation))
        causation.add((node, EXT.manifestsSymptom, DOM[rule.symptom]))
        causation.add((node, EXT.hasMechanism, _rule_mechanism(rule)))
        cond = _rule_condition(rule)
        if cond is not None:
            causation.add((node, EXT.underCondition, cond))
        causation.add((node, EXT.causationPolarity, Literal(rule.polarity)))
        causation.add((node, DOM.fromSentence, DOM[rule.id]))  # 프로비넌스: 파생 규칙 역참조

        if not rule.makes_gate:
            # mitigate 는 원인의 여집합 — 게이트를 만들지 않고 근거로만 보존한다.
            continue

        shape = DOM[rule.shape_id]
        where = " ".join(cond_to_sparql(c) for c in rule.conds)
        message = f"[{rule.basis}] {rule.label}"

        shapes.add((shape, RDF.type, SH.NodeShape))
        shapes.add((shape, SH.targetClass, DOM.WiperBlade))
        shapes.add((shape, DOM.gateFor, DOM[rule.symptom]))
        shapes.add((shape, DOM.sentence, Literal(rule.basis)))
        sp = BNode()
        shapes.add((shape, SH.sparql, sp))
        shapes.add((sp, SH.severity, SH.Violation))
        shapes.add((sp, SH.message, Literal(message)))
        shapes.add((sp, SH.select, Literal(f"SELECT $this WHERE {{ {where} }}")))

        gates[rule.shape_id] = Gate(
            shape_id=rule.shape_id,
            rule_id=rule.id,
            symptom=rule.symptom,
            basis=rule.basis,
            polarity=rule.polarity,
            category=rule.category,
            message=message,
        )

    return CompiledRules(
        shapes=shapes,
        causal=causal,
        human_view=human,
        gates=gates,
        applied_rules=applied,
        applied_categories=_ordered_categories(rules, categories),
        shapes_hash=hashlib.sha256(shapes.serialize(format="nt").encode("utf-8")).hexdigest()[:16],
        causation=causation,
        causation_shape=causation_shape_graph(),
    )


def _ordered_categories(rules: list[RuleSpec], categories: set[str] | None) -> list[str]:
    """카테고리를 **근거 문장 번호 순**으로 정렬한다 (소음=S1 → 떨림=S3).

    가나다순이면 '떨림'이 앞서 계약 fixture 와 어긋나고, 집합 순서면 비결정적이다.
    문장 순서는 도메인 서술 순서라 사람이 읽기에도 자연스럽다.
    """
    selected = categories if categories is not None else {r.category for r in rules}
    first_sentence: dict[str, tuple[int, str]] = {}
    for rule in rules:
        if rule.category not in selected:
            continue
        key = min((sentence_sort_key(s) for s in rule.basis_sentences), default=(1 << 30, rule.category))
        current = first_sentence.get(rule.category)
        if current is None or key < current:
            first_sentence[rule.category] = key
    # 규칙이 하나도 없는 카테고리(오타 등)는 뒤로 보내되 이름순으로 안정 정렬
    return sorted(selected, key=lambda c: first_sentence.get(c, (1 << 30, c)))


class RuleCompiler:
    """`core.protocols.RuleCompiler` 구현. 컴파일 결과는 카테고리 조합 단위로 캐시한다.

    T-93 — 규칙의 진실원은 **시드 `rules.ttl` + 저작 오버레이**다. 저작이 규칙을 추가하면
    (오버레이 파일 변경) 다음 컴파일에서 자동으로 반영된다(mtime 재로드 + 캐시 무효화).
    오버레이가 비어 있으면 시드와 완전히 같은 결과 → **시드 회귀 불변**.
    """

    def __init__(self, ontology_dir: Path | None = None, authoring_rules_path: Path | None = None) -> None:
        self._dir = ontology_dir or settings.ontology_dir
        self._authoring_path = authoring_rules_path or settings.authoring_rules_path
        self._sentence_polarity = load_sentence_polarity(self._dir / "m1_wiper.ttl")
        self._seed_rules = load_rules(self._dir / "rules.ttl")
        self._authored_rules: list[RuleSpec] = []
        self._authoring_mtime: float | None = None
        self._reload_authored()

    def _authoring_stamp(self) -> float | None:
        return self._authoring_path.stat().st_mtime if self._authoring_path.exists() else None

    def _reload_authored(self) -> None:
        self._authoring_mtime = self._authoring_stamp()
        self._authored_rules = (
            load_rules(self._authoring_path) if self._authoring_path.exists() else []
        )

    def _maybe_reload(self) -> None:
        """저작 오버레이가 바뀌었으면 다시 읽고 컴파일 캐시를 버린다(저작 → 판정 즉시 반영)."""
        if self._authoring_stamp() != self._authoring_mtime:
            self._reload_authored()
            self._compile_cached.cache_clear()

    @property
    def rules(self) -> list[RuleSpec]:
        self._maybe_reload()
        return [*self._seed_rules, *self._authored_rules]

    @property
    def sentence_polarity(self) -> dict[str, str]:
        return self._sentence_polarity

    def compile(self, categories: set[str] | None = None) -> CompiledRules:
        self._maybe_reload()
        return self._compile_cached(frozenset(categories) if categories is not None else None)

    @lru_cache(maxsize=32)  # noqa: B019 — 인스턴스 수명 = 프로세스 수명
    def _compile_cached(self, categories: frozenset[str] | None) -> CompiledRules:
        rules = [*self._seed_rules, *self._authored_rules]
        return compile_rules(rules, set(categories) if categories is not None else None)

    def gate_count(self, categories: set[str] | None = None) -> int:
        return len(self.compile(categories).gates)
