/**
 * AI Gateway 계약 타입 — `interface_contracts.md` §3.
 * BFF 는 LLM 생성(추출 초안·RB 파싱·자연어 답변·질의 분류)만 한다.
 * 판정(satisfies·conforms·violations)은 절대 LLM 출력으로 채우지 않는다 (불변원칙 3).
 */

export type ConceptType =
  | "PartType" | "Component" | "Material" | "VehicleType"
  | "EnvCondition" | "Symptom" | "Behavior" | "Attribute";

export type Predicate =
  | "causes" | "mitigates" | "aggravates" | "conditionedOn"
  | "hasMaterial" | "has_part" | "mountedOn" | "operatesIn";

export const CONCEPT_TYPES: ReadonlySet<ConceptType> = new Set([
  "PartType", "Component", "Material", "VehicleType",
  "EnvCondition", "Symptom", "Behavior", "Attribute",
]);

export const PREDICATES: ReadonlySet<Predicate> = new Set([
  "causes", "mitigates", "aggravates", "conditionedOn",
  "hasMaterial", "has_part", "mountedOn", "operatesIn",
]);

export interface Concept {
  label: string;
  type: ConceptType;
  iri?: string;
  span?: [number, number];
}

export interface Relation {
  subject: string;
  predicate: Predicate;
  object: string;
  evidence?: string;
  confidence?: number;
}

export interface Source {
  sentence?: string;
  rule?: string;
  iri?: string;
  text?: string;
}

/** 추출 SSE 이벤트 (지식서비스 검증 이전, LLM 산출 초안). */
export type ExtractionEvent =
  | { kind: "status"; stage: "extract" | "validate"; msg?: string }
  | { kind: "concept"; concept: Concept }
  | { kind: "relation"; relation: Relation };

export interface RequirementDraft {
  /** 자연어 → RB 초안. 증상 존재 검증은 지식서비스가 한다(BFF 는 생성만). */
  forbids_symptom: string;
  label: string;
}

export type ProviderName = "mock" | "claude" | "gemini";

export interface AIProvider {
  readonly name: ProviderName;
  /** structured output, 결정론(temperature 0~0.2 또는 그 등가). type·predicate 열거형 밖 금지. */
  extract(text: string): AsyncIterable<ExtractionEvent>;
  parseRequirements(text: string): Promise<RequirementDraft[]>;
  /**
   * CD-14: 검증 답변 전용. **`context` 가 비면 throw** — 근거 없는 답변을 지어내지 않는다.
   * 무근거 단독 답변이 필요하면 `llmOnlyAnswer` 를 써라(환각비교 전용).
   */
  answer(question: string, context: Source[]): Promise<string>;
  /** CD-14: 무근거 LLM 단독 답변. **환각비교의 `llm_answer` 에만** 쓴다. verified_answer 에 절대 쓰지 않는다. */
  llmOnlyAnswer(question: string): Promise<string>;
  /** Q&A 라우팅 분류. structured output {"layer":"A|B|C"}, temperature 0. */
  classify(question: string): Promise<"A" | "B" | "C">;
}

/** CD-14: 근거 없는 검증 답변 시도. 프로그래밍 오류(막다른 길에서 LLM 흘러내림)를 타입으로 막는다. */
export class EmptyContextError extends Error {
  constructor() {
    super("answer() requires non-empty sources; use llmOnlyAnswer() for no-context answers");
    this.name = "EmptyContextError";
  }
}
