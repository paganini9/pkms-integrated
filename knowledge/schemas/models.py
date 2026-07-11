"""Pydantic 모델 — `_coordination/contracts/schemas/*.json` v1 의 코드 표현.

계약이 진실원이다. 이 파일을 고치기 전에 계약을 먼저 고치고(변경 절차),
`python _coordination/contracts/validate_contracts.py` 가 통과하는지 확인한다.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── 열거형 (범주 밖 값은 추출 단계에서 unknown_concept 위반으로 걸린다) ────────
ConceptType = Literal[
    "PartType", "Component", "Material", "VehicleType", "EnvCondition", "Symptom", "Behavior", "Attribute"
]
Predicate = Literal[
    "causes", "mitigates", "aggravates", "conditionedOn", "hasMaterial", "has_part", "mountedOn", "operatesIn"
]
Polarity = Literal["cause", "mitigate", "aggravate"]
Severity = Literal["violation", "warning"]
ViolationCode = Literal["causes_range", "disjoint", "shacl_constraint", "missing_required", "unknown_concept"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 공통 타입 ──────────────────────────────────────────────────────────────
class Concept(Strict):
    label: str = Field(min_length=1)
    type: ConceptType
    iri: str | None = None
    span: tuple[int, int] | None = None


class Relation(Strict):
    subject: str = Field(min_length=1)
    predicate: Predicate
    object: str = Field(min_length=1)
    evidence: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class Violation(Strict):
    """CD-7: severity=violation → UI amber + 저장 차단. warning → 정보 표시 + 저장 허용."""

    code: ViolationCode
    severity: Severity
    offender: str = Field(min_length=1)
    offender_iri: str | None = None
    message: str = Field(min_length=1)
    sentence: str | None = None
    source_shape: str | None = None


class Source(Strict):
    iri: str
    sentence: str | None = None
    rule: str | None = None
    text: str | None = None


class Design(Strict):
    """CD-8 — 수치·형상은 선택. 결측은 422 가 아니라 `satisfies:null` 판정 보류로 간다."""

    material: Literal["Rubber", "Silicone"]
    vehicle: Literal["MidSizeSUV", "CompactSedan"]
    id: str | None = None
    label: str | None = None
    length_mm: Annotated[int, Field(gt=0, le=2000)] | None = None
    spring_n: Annotated[int, Field(gt=0, le=1000)] | None = None
    arm_shape: Literal["simple", "complex"] | None = None
    env: Literal["Winter"] | None = None


# ── 추출 · 검증 · 저장 (FR-01~03·3d) ───────────────────────────────────────
class ValidateRequest(Strict):
    concepts: list[Concept]
    relations: list[Relation]
    project_id: str | None = None


class ValidateResponse(Strict):
    conforms: bool
    violations: list[Violation]
    trace_id: str


class DesignRuleCond(Strict):
    path: str
    op: Literal["eq", "lt", "le", "gt", "ge", "gtPath"]
    val: str | int | float | None = None
    ref_list: list[str] | None = None


class DerivedRule(Strict):
    id: str
    label: str
    polarity: Polarity
    category: str
    about_symptom: str | None = None
    basis: str | None = None
    conds: list[DesignRuleCond]


class DerivedShape(Strict):
    id: str
    gate_for: str
    sentence: str


class SavedSentence(Strict):
    id: str
    iri: str
    text: str
    category: str
    mentions: list[str]
    about_symptom: str | None = None
    polarity: Polarity


class Derived(Strict):
    rule: DerivedRule
    shapes: list[DerivedShape]
    causal_edges: list[Relation]


class SaveRequest(Strict):
    sentence_text: str = Field(min_length=1, max_length=2000)
    concepts: list[Concept]
    relations: list[Relation]
    category: str = Field(min_length=1)
    approved: Literal[True]  # HITL 게이트 — false 는 스키마 단계에서 거부
    draft_id: str | None = None
    project_id: str | None = None


class SaveResponse(Strict):
    sentence: SavedSentence
    derived: Derived
    human_view: list[str]
    trace_id: str


# ── satisfy (FR-04·05) ────────────────────────────────────────────────────
class IntervalCheck(Strict):
    name: str
    expr: str
    ok: bool


class ExhibitedSymptom(Strict):
    symptom: str
    label: str
    sentences: list[str]  # 게이트 basis 원문. 예 ["S3,S5", "S4"]


class SubsumptionStep(Strict):
    stage: Literal["subsumption"] = "subsumption"
    ok: bool
    detail: str


class ShaclIntervalStep(Strict):
    stage: Literal["shacl_interval"] = "shacl_interval"
    ok: bool
    checks: list[IntervalCheck]
    warnings: list[Violation] | None = None


class SymptomFreeStep(Strict):
    stage: Literal["symptom_free"] = "symptom_free"
    ok: bool
    exhibited: list[ExhibitedSymptom]


Step = Annotated[SubsumptionStep | ShaclIntervalStep | SymptomFreeStep, Field(discriminator="stage")]


class ViolatedRequirement(Strict):
    rb: str
    label: str | None = None
    forbids: str
    sentences: list[str]


class SatisfyRequest(Strict):
    design: Design
    project_id: str | None = None
    require: list[str] = Field(default_factory=list)
    categories: list[str] | None = None  # CD-4: 컴파일 시점 필터. None = 전체


class SatisfyResponse(Strict):
    """판정 주체는 reasoner/SHACL. LLM 출력으로 satisfies/violations 를 채우지 않는다."""

    satisfies: bool | None  # None = 판정 보류 (pending_reason)
    steps: list[Step] = Field(min_length=3, max_length=3)
    violations: list[str]  # CD-1 정규화 (cause·aggravate 문장만, 정렬·중복제거)
    violation_bases: list[str]  # CD-1 원본 basis
    violated_requirements: list[ViolatedRequirement]
    alternatives: list[str]
    trace_id: str
    pending_reason: Literal["missing_required"] | None = None
    applied_categories: list[str] = Field(default_factory=list)
    justification: list[str] = Field(default_factory=list)
    cache_hit: bool = False


# ── Q&A · RAG (FR-06~09) ──────────────────────────────────────────────────
class RagHit(Strict):
    iri: str
    text: str
    score: float
    verified: bool  # 파생 규칙이 SPARQL/SHACL 검증을 통과했는가
    sentence: str | None = None
    about_symptom: str | None = None
    derives_rule: str | None = None


class RagSearchRequest(Strict):
    query: str = Field(min_length=1)
    k: int = Field(default=6, ge=1, le=50)
    project_id: str | None = None


class RagSearchResponse(Strict):
    hits: list[RagHit]
    sufficient: bool  # verified=True hit >= 1
    trace_id: str


class VerifiedAnswer(Strict):
    text: str
    determinism: Literal["sparql", "satisfy", "rag"]
    sources: list[Source]  # C계층은 verified=True hit 만 (미검증 근거 0)


class LlmAnswer(Strict):
    text: str
    model: Literal["mock", "claude", "gemini"]


class Mismatch(Strict):
    claim: str
    verdict: str
    evidence: list[str] = Field(default_factory=list)


class Comparison(Strict):
    mismatches: list[Mismatch]
    violation_rate: float = Field(ge=0, le=1)
    agreement_rate: float = Field(ge=0, le=1)


class QaResponse(Strict):
    layer: Literal["A", "B", "C"]
    verified_answer: VerifiedAnswer
    insufficient_evidence: bool
    trace_id: str
    llm_answer: LlmAnswer | None = None
    comparison: Comparison | None = None


# ── 프로젝트 · 지식범위 (FR-3b·3c) ─────────────────────────────────────────
class Requirement(Strict):
    id: str
    label: str
    forbids_symptom: str
    iri: str | None = None


class KnowledgeScopeRequest(Strict):
    categories: list[str]


class KnowledgeScopeResponse(Strict):
    categories: list[str]
    compiled_gates: int
    trace_id: str


# ── 지식맵 (FR-10) ────────────────────────────────────────────────────────
class GraphNode(Strict):
    id: str
    label: str
    kind: Literal["concept", "sentence", "rule", "symptom", "design", "requirement", "class"]
    iri: str
    layer: Literal["M0", "M1", "M2"] | None = None
    inferred: bool = False
    text: str | None = None


class GraphEdge(Strict):
    source: str
    target: str
    predicate: str
    inferred: bool = False  # true → 프론트 점선 (AC-4)
    evidence: str | None = None


class GraphStats(Strict):
    nodes: int
    edges: int
    inferred_edges: int = 0
    truncated: bool = False


class GraphResponse(Strict):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    stats: GraphStats
    trace_id: str


# ── kg/lookup (CD-11) ─────────────────────────────────────────────────────
class LookupResponse(Strict):
    """화이트리스트 명명 질의 결과. `rows` 는 질의별 스키마라 자유 dict, `sources` 는 문장 근거."""

    query: str
    rows: list[dict]
    sources: list[Source]
    trace_id: str


# ── health ────────────────────────────────────────────────────────────────
class HealthResponse(Strict):
    status: Literal["ok", "degraded"]
    store: str
    reasoner: str
    rag: str
    trace_id: str
