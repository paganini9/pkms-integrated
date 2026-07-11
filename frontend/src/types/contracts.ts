/**
 * 계약 타입 — `_coordination/contracts/schemas/*.json` v1 의 TS 표현.
 * 계약이 진실원이다. 여기를 고치기 전에 계약을 먼저 고친다(변경 절차).
 */

export type ConceptType =
  | "PartType" | "Component" | "Material" | "VehicleType"
  | "EnvCondition" | "Symptom" | "Behavior" | "Attribute";

export type Predicate =
  | "causes" | "mitigates" | "aggravates" | "conditionedOn"
  | "hasMaterial" | "has_part" | "mountedOn" | "operatesIn";

export type Polarity = "cause" | "mitigate" | "aggravate";

export interface Concept { label: string; type: ConceptType; iri?: string; span?: [number, number] }
export interface Relation { subject: string; predicate: Predicate; object: string; evidence?: string; confidence?: number }

/** CD-7 — severity: "violation" 은 amber 로 표시하고 승인 버튼을 비활성화한다. */
export interface Violation {
  code: "causes_range" | "disjoint" | "shacl_constraint" | "missing_required" | "unknown_concept";
  severity: "violation" | "warning";
  offender: string;
  offender_iri?: string;
  message: string;
  sentence?: string;
  source_shape?: string;
}

export interface Source { iri: string; sentence?: string; rule?: string; text?: string }

/** CD-8 — 수치·형상은 선택. 누락은 검증 오류가 아니라 satisfies:null 판정 보류. */
export interface Design {
  id?: string; label?: string;
  material: "Rubber" | "Silicone";
  vehicle: "MidSizeSUV" | "CompactSedan";
  length_mm?: number | null;
  spring_n?: number | null;
  arm_shape?: "simple" | "complex" | null;
  env?: "Winter" | null;
}

// ── SSE (api_standard.md §4.1) ────────────────────────────────────────────
export type StreamEvent =
  | { event: "status"; data: { stage: "extract" | "validate"; msg?: string } }
  | { event: "concept"; data: Concept }
  | { event: "relation"; data: Relation }
  | { event: "validation"; data: { conforms: boolean; violations: Violation[] } }
  | { event: "done"; data: { thread_id: string; draft_id: string; trace_id: string } }
  | { event: "error"; data: ApiError };

export interface ApiError { code: string; user_message: string; trace_id: string; details?: Record<string, unknown> }

// ── satisfy ──────────────────────────────────────────────────────────────
export interface IntervalCheck { name: string; expr: string; ok: boolean }
export interface ExhibitedSymptom { symptom: string; label: string; sentences: string[] }

export type Step =
  | { stage: "subsumption"; ok: boolean; detail: string }
  | { stage: "shacl_interval"; ok: boolean; checks: IntervalCheck[]; warnings?: Violation[] }
  | { stage: "symptom_free"; ok: boolean; exhibited: ExhibitedSymptom[] };

export interface ViolatedRequirement { rb: string; label?: string; forbids: string; sentences: string[] }

export interface SatisfyResponse {
  /** null = 판정 보류 (pending_reason 참조). 결정론 엔진 산출 — LLM 아님. */
  satisfies: boolean | null;
  pending_reason?: "missing_required" | null;
  applied_categories?: string[];
  steps: Step[];
  /** CD-1: 개별 문장 코드 (cause·aggravate 만). 예 ["S1","S3","S4","S6"] */
  violations: string[];
  /** CD-1: 게이트 원본 basis. 예 ["S1","S3,S5","S4","S6"] */
  violation_bases: string[];
  violated_requirements: ViolatedRequirement[];
  alternatives: string[];
  justification?: string[];
  cache_hit?: boolean;
  trace_id: string;
}

// ── Q&A ──────────────────────────────────────────────────────────────────
export interface VerifiedAnswer { text: string; determinism: "sparql" | "satisfy" | "rag"; sources: Source[] }
export interface LlmAnswer { text: string; model: "mock" | "claude" | "gemini" }
export interface Mismatch { claim: string; verdict: string; evidence?: string[] }
export interface Comparison { mismatches: Mismatch[]; violation_rate: number; agreement_rate: number }

export interface QaResponse {
  layer: "A" | "B" | "C";
  verified_answer: VerifiedAnswer;
  /** true 면 "명세 근거 없음"을 명시한다. 억지 답 금지. */
  insufficient_evidence: boolean;
  llm_answer?: LlmAnswer | null;
  comparison?: Comparison | null;
  trace_id: string;
}

// ── extraction/validate · save (§4.2 · §4.3) ─────────────────────────────
export interface ValidateResponse { conforms: boolean; violations: Violation[]; trace_id: string }

export interface SavedSentence {
  id: string; iri: string; text: string; category: string;
  mentions: string[]; about_symptom: string; polarity: Polarity;
}
export interface DerivedRule {
  id: string; label: string; polarity: Polarity; category: string;
  about_symptom?: string; basis?: string;
  conds: { path: string; op: string; val: string }[];
}
export interface DerivedShape { id: string; gate_for: string; sentence: string }
export interface CausalEdge { subject: string; predicate: string; object: string; evidence?: string }
export interface SaveResponse {
  sentence: SavedSentence;
  derived: { rule: DerivedRule; shapes: DerivedShape[]; causal_edges: CausalEdge[] };
  human_view: string[];
  trace_id: string;
}

// ── 프로젝트 (§4.7) ────────────────────────────────────────────────────────
export interface ProjectResponse {
  id: string; iri?: string; name: string;
  target_vehicle?: string; target_env?: string;
  knowledge_categories: string[];
  requirements?: RequirementBehavior[];
  designs?: unknown[];
  trace_id?: string;
}

// ── 프로젝트 요구사항 (§4.7, AC-1P) ────────────────────────────────────────
export interface RequirementBehavior { id: string; iri?: string; label: string; forbids_symptom: string }
export interface RequirementsResponse {
  requirements: RequirementBehavior[];
  unknown_symptoms: string[];
  trace_id: string;
}

// ── health (§4.10) ─────────────────────────────────────────────────────────
export interface HealthResponse {
  status: "ok" | "degraded";
  llm_provider: "mock" | "claude" | "gemini";
  knowledge?: { status: string; store: string; reasoner: string; rag: string };
  trace_id: string;
}

// ── 지식맵 ────────────────────────────────────────────────────────────────
export interface GraphNode {
  id: string; label: string;
  kind: "concept" | "sentence" | "rule" | "symptom" | "design" | "requirement" | "class";
  iri: string; layer?: "M0" | "M1" | "M2"; inferred?: boolean; text?: string;
}
/** inferred: true → 점선 렌더 (AC-4) */
export interface GraphEdge { source: string; target: string; predicate: string; inferred?: boolean; evidence?: string }
export interface GraphResponse {
  nodes: GraphNode[]; edges: GraphEdge[];
  stats: { nodes: number; edges: number; inferred_edges?: number; truncated?: boolean };
  trace_id: string;
}
