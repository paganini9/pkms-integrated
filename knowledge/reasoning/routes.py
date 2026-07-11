"""04 그래프·코어 라우터 — 내부 API (prefix 없음).

`/validate/shacl` · `/reason/consistency` · `/reason/classify` · `/satisfy` · `/rules/compile` · `/rules/dry-run`

import 부작용 금지 — 엔진은 `get_*()` 의존성에서 처음 만든다(TTL 파싱이 무겁다).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from rdflib import Graph

from core.logging import get_trace_id
from reasoning.compiler import RuleCompiler
from reasoning.reasoner import Reasoner
from reasoning.rule_views import RuleViews
from reasoning.satisfy import SatisfyEngine
from reasoning.spec_validate import SpecValidator
from reasoning.upper_ontology import UpperOntology
from schemas.errors import NotFound, ValidationError
from schemas.models import (
    SatisfyRequest,
    SatisfyResponse,
    Strict,
    ValidateRequest,
    ValidateResponse,
)

router = APIRouter(tags=["reasoning"])


@lru_cache(maxsize=1)
def get_compiler() -> RuleCompiler:
    return RuleCompiler()


@lru_cache(maxsize=1)
def get_engine() -> SatisfyEngine:
    return SatisfyEngine(compiler=get_compiler())


@lru_cache(maxsize=1)
def get_reasoner() -> Reasoner:
    return Reasoner()


@lru_cache(maxsize=1)
def get_spec_validator() -> SpecValidator:
    return SpecValidator()


@lru_cache(maxsize=1)
def get_upper_ontology() -> UpperOntology:
    return UpperOntology()


def get_rule_views() -> RuleViews:
    return RuleViews(get_engine())


# ── 명세 검증 (FR-02) ─────────────────────────────────────────────────────
@router.post("/validate/shacl", response_model=ValidateResponse)
def validate_shacl(
    req: ValidateRequest, validator: Annotated[SpecValidator, Depends(get_spec_validator)]
) -> ValidateResponse:
    violations = validator.validate(req.concepts, req.relations)
    return ValidateResponse(
        conforms=not any(v.severity == "violation" for v in violations),
        violations=violations,
        trace_id=get_trace_id(),
    )


# ── OOV 매핑 후보 (T-89) ───────────────────────────────────────────────────
class OovCandidatesRequest(BaseModel):
    label: str = Field(min_length=1)
    k: int = 3


class OovCandidate(BaseModel):
    concept: str
    iri: str
    pref_label: str
    score: float
    via: str


class OovCandidatesResponse(BaseModel):
    label: str
    in_domain: bool
    candidates: list[OovCandidate]
    provisional: bool = True  # 승인(altLabel 편입) 전엔 접지에 쓰이지 않는다 — fail-closed 불변
    trace_id: str


@router.post("/oov/candidates", response_model=OovCandidatesResponse)
def oov_candidates(
    req: OovCandidatesRequest, validator: Annotated[SpecValidator, Depends(get_spec_validator)]
) -> OovCandidatesResponse:
    """온톨로지 밖 라벨의 매핑 후보(어휘 유사도 + 임베딩 최근접). 후보는 provisional."""
    from reasoning.oov import candidates as gen_candidates

    embedder = None
    try:
        from rag.routes import get_retriever

        embedder = get_retriever().embedder
    except Exception:  # noqa: BLE001 — 임베더 없으면 어휘 후보만
        embedder = None
    cands = gen_candidates(req.label, validator, embedder, req.k)
    return OovCandidatesResponse(
        label=req.label,
        in_domain=validator.concept_in_domain(req.label),
        candidates=[OovCandidate(concept=c.concept, iri=c.iri, pref_label=c.pref_label, score=c.score, via=c.via) for c in cands],
        trace_id=get_trace_id(),
    )


# ── satisfy (FR-04·05) ────────────────────────────────────────────────────
@router.post("/satisfy", response_model=SatisfyResponse)
def satisfy(req: SatisfyRequest, engine: Annotated[SatisfyEngine, Depends(get_engine)]) -> SatisfyResponse:
    categories = set(req.categories) if req.categories is not None else None
    return engine.satisfy(req.design, req.require, categories)


# ── 추론 (FR-12) ──────────────────────────────────────────────────────────
class ConsistencyRequest(Strict):
    ttl: str | None = Field(default=None, description="검사할 추가 트리플(turtle). 생략 시 시드 온톨로지")


class ConsistencyResponse(Strict):
    consistent: bool
    clashes: list[str]
    engine: str
    trace_id: str


@router.post("/reason/consistency", response_model=ConsistencyResponse)
def consistency(
    req: ConsistencyRequest, reasoner: Annotated[Reasoner, Depends(get_reasoner)]
) -> ConsistencyResponse:
    graph = reasoner._load_onto()  # noqa: SLF001 — 같은 레이어
    if req.ttl:
        try:
            graph.parse(data=req.ttl, format="turtle")
        except Exception as exc:
            raise ValidationError(f"turtle 파싱 실패: {exc}", details={"field": "ttl"}) from exc

    result = reasoner.consistency(graph)
    return ConsistencyResponse(
        consistent=result.consistent, clashes=result.clashes, engine=result.engine, trace_id=get_trace_id()
    )


class ClassifyRequest(Strict):
    iri: str


class ClassifyResponse(Strict):
    iri: str
    types: list[str]
    trace_id: str


@router.post("/reason/classify", response_model=ClassifyResponse)
def classify(req: ClassifyRequest, reasoner: Annotated[Reasoner, Depends(get_reasoner)]) -> ClassifyResponse:
    types = reasoner.classify(req.iri)
    if not types:
        raise NotFound(f"개체 {req.iri} 의 타입을 추론할 수 없음")
    return ClassifyResponse(iri=req.iri, types=types, trace_id=get_trace_id())


# ── 규칙 컴파일 (FR-3d·13) ────────────────────────────────────────────────
class CompileRequest(Strict):
    categories: list[str] | None = None


class CompiledRuleView(Strict):
    id: str
    label: str
    polarity: str
    category: str
    basis: str
    about_symptom: str
    makes_gate: bool


class CompileResponse(Strict):
    rules: list[CompiledRuleView]
    shapes: list[str]
    gate_rules: list[str]
    human_view: list[str]
    applied_categories: list[str]
    shapes_ttl: str
    trace_id: str


@router.post("/rules/compile", response_model=CompileResponse)
def compile_rules(
    req: CompileRequest, compiler: Annotated[RuleCompiler, Depends(get_compiler)]
) -> CompileResponse:
    """CD-4 — 카테고리 필터는 컴파일 시점에 적용된다. 판정 후 필터링이 아니다."""
    categories = set(req.categories) if req.categories is not None else None
    compiled = compiler.compile(categories)
    return CompileResponse(
        rules=[
            CompiledRuleView(
                id=r.id,
                label=r.label,
                polarity=r.polarity,
                category=r.category,
                basis=r.basis,
                about_symptom=r.symptom,
                makes_gate=r.makes_gate,
            )
            for r in compiled.applied_rules
        ],
        shapes=sorted(compiled.gates),
        gate_rules=sorted(compiled.gate_rules),
        human_view=compiled.human_view,
        applied_categories=compiled.applied_categories,
        shapes_ttl=compiled.shapes.serialize(format="turtle"),
        trace_id=get_trace_id(),
    )


# ── dry-run (FR-13 · AC-7) ────────────────────────────────────────────────
class DryRunRequest(Strict):
    """규칙·수치 변경을 임시 그래프에 적용해 새 위반을 미리 본다. 저장하지 않는다."""

    override_ttl: str = Field(description="임시로 덮어쓸 트리플(turtle). 예: MidSizeSUV maxSafeLengthMm 595")
    categories: list[str] | None = None


class DryRunResponse(Strict):
    new_violations: list[str]
    affected_instances: list[str]
    trace_id: str


@router.post("/rules/dry-run", response_model=DryRunResponse)
def dry_run(
    req: DryRunRequest,
    compiler: Annotated[RuleCompiler, Depends(get_compiler)],
    engine: Annotated[SatisfyEngine, Depends(get_engine)],
) -> DryRunResponse:
    try:
        override = Graph().parse(data=req.override_ttl, format="turtle")
    except Exception as exc:
        raise ValidationError(f"turtle 파싱 실패: {exc}", details={"field": "override_ttl"}) from exc

    categories = set(req.categories) if req.categories is not None else None
    new_violations, affected = engine.dry_run(override, categories)
    return DryRunResponse(new_violations=new_violations, affected_instances=affected, trace_id=get_trace_id())


# ── CD-10 · FR-12 · AC-6: 상위 온톨로지 ────────────────────────────────────
class UpperEditRequest(Strict):
    changes: list[dict]
    approved: bool = False


class UpperImpactRequest(Strict):
    changes: list[dict]


@router.get("/upper-ontology/classes")
def upper_classes(uo: Annotated[UpperOntology, Depends(get_upper_ontology)]) -> dict:
    return uo.classes()


@router.post("/upper-ontology/classes")
def upper_edit(
    req: UpperEditRequest, uo: Annotated[UpperOntology, Depends(get_upper_ontology)]
) -> dict:
    """HITL 게이트 — approved!=true 면 409 GUARDRAIL_BLOCKED (불변원칙 4)."""
    return uo.edit(req.changes, req.approved)


@router.post("/upper-ontology/impact")
def upper_impact(
    req: UpperImpactRequest, uo: Annotated[UpperOntology, Depends(get_upper_ontology)]
) -> dict:
    return uo.impact(req.changes)


# ── CD-10 · FR-13: 규칙 조회(읽기 전용 — PUT/PATCH 없음) ─────────────────────
@router.get("/rules")
def rules_list(views: Annotated[RuleViews, Depends(get_rule_views)]) -> dict:
    return views.list()


@router.get("/rules/{rule_id}/impact")
def rules_impact(rule_id: str, views: Annotated[RuleViews, Depends(get_rule_views)]) -> dict:
    return views.impact(rule_id)
