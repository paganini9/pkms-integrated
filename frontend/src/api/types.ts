/** API 경계 공통 타입 — mock/real 구현이 공유한다. */
import type {
  ApiError, Concept, Relation, Violation,
  GraphResponse, HealthResponse, QaResponse, SatisfyResponse,
  ValidateResponse, SaveResponse, RequirementsResponse, Design, ProjectResponse,
} from "../types/contracts";

// ── provider (T-90 모델 스위치) ─────────────────────────────────────────────
export type Provider = "solar" | "claude" | "gemini" | "mock";

// ── SSE (extraction/stream) ────────────────────────────────────────────────
export interface StreamRequest { text: string; thread_id?: string; project_id?: string; provider?: Provider }

// A/B diff (T-90) — 두 모델로 추출 비교.
export interface ABExtractRequest { text: string; providers?: Provider[] }
export interface ABResult { requested_provider: Provider; actual_provider: Provider; concepts: Concept[]; relations: Relation[]; error?: string }
export interface ABExtractResponse { text: string; results: ABResult[]; trace_id: string }

export interface StreamHandlers {
  onStatus?: (d: { stage: "extract" | "validate" | "provider"; msg?: string; provider?: Provider; requested_provider?: Provider; fallback?: boolean }) => void;
  onConcept?: (c: Concept) => void;
  onRelation?: (r: Relation) => void;
  onValidation?: (d: { conforms: boolean; violations: Violation[] }) => void;
  onDone?: (d: { thread_id: string; draft_id: string; trace_id: string }) => void;
  /** SSE §5: error 수신 시 렌더 유지 + "다시 시도". 자동 재연결 금지. */
  onError?: (e: ApiError) => void;
}

export interface StreamController { cancel: () => void }

export interface ValidateRequest { concepts: Concept[]; relations: Relation[]; project_id?: string }

export interface SaveRequest {
  sentence_text: string;
  concepts: Concept[];
  relations: Relation[];
  category: string;
  approved: boolean;
  draft_id?: string;
  project_id?: string;
}

export interface SatisfyRequest {
  project_id: string;
  design: Design;
  require?: string[];
  categories?: string[];
}

export interface QaRequest {
  question: string;
  mode: "compare" | "verified";
  project_id?: string;
  thread_id?: string;
}

export interface RequirementsRequest { text: string }

export interface CreateProjectRequest {
  name: string;
  target_vehicle?: string;
  target_env?: string;
  knowledge_categories?: string[];
}

/** mock/real 이 동일하게 구현하는 API 경계. */
export interface PkmsApi {
  health(): Promise<HealthResponse>;
  extractionStream(req: StreamRequest, h: StreamHandlers): StreamController;
  extractionAB(req: ABExtractRequest): Promise<ABExtractResponse>;
  extractionValidate(req: ValidateRequest): Promise<ValidateResponse>;
  extractionSave(req: SaveRequest): Promise<SaveResponse>;
  satisfy(req: SatisfyRequest): Promise<SatisfyResponse>;
  qa(req: QaRequest): Promise<QaResponse>;
  graph(params: Record<string, string>): Promise<GraphResponse>;
  createProject(req: CreateProjectRequest): Promise<ProjectResponse>;
  parseRequirements(projectId: string, req: RequirementsRequest): Promise<RequirementsResponse>;
}

/** 사용자에게는 user_message(다음 행동)만 노출. 내부 원인·스택 금지. */
export class ApiCallError extends Error {
  constructor(public readonly body: ApiError) {
    super(body.user_message ?? "일시적인 오류입니다.");
  }
}
