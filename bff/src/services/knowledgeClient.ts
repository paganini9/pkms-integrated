/**
 * 지식서비스 클라이언트 — BFF 가 지식에 접근하는 **유일한 경로**.
 * 여기서 RDF/SPARQL/SHACL 문자열을 만들지 않는다 (불변원칙 1). 판정은 지식서비스가, BFF 는 통과만.
 * CD-11: `sparql(query)` 는 제거되었다. A계층은 `kgLookup`(명명 질의)만 쓴다.
 * 계약: `interface_contracts.md` §1·§1.2.
 *
 * T-55(지식서비스)가 동시 구현 중이라 신설 엔드포인트가 아직 없을 수 있다.
 * `config.knowledgeMock` 이면 contracts/mocks 를 반환하는 mock 으로 선행한다(병렬 규약).
 */
import { config } from "../core/config.js";
import { AppError, KnowledgeUnavailable } from "../core/errors.js";
import { createKnowledgeMock } from "./knowledgeMock.js";

export interface Violation {
  code: "causes_range" | "disjoint" | "shacl_constraint" | "missing_required" | "unknown_concept";
  severity: "violation" | "warning";
  offender: string;
  offender_iri?: string;
  message: string;
  sentence?: string;
  source_shape?: string;
}

export interface ValidateRes {
  conforms: boolean;
  violations: Violation[];
  trace_id: string;
}

export interface RagHit {
  iri: string;
  sentence: string;
  text: string;
  score: number;
  about_symptom?: string;
  derives_rule?: string;
  verified: boolean;
}

export interface RagRes {
  hits: RagHit[];
  sufficient: boolean;
  trace_id: string;
}

export interface LookupSource {
  sentence?: string;
  rule?: string;
  iri?: string;
  text?: string;
}

export interface LookupRes {
  query: string;
  rows: Array<Record<string, unknown>>;
  sources: LookupSource[];
  trace_id: string;
}

export type NamedQuery = "max_safe_length" | "symptom_causes" | "rule_sentences" | "concept_relations";

export interface GraphQuery {
  layer?: string | undefined;
  symptom?: string | undefined;
  sentence?: string | undefined;
  project_id?: string | undefined;
  limit?: number | undefined;
}

export interface KnowledgeClient {
  health(): Promise<Record<string, unknown>>;
  validateShacl(req: unknown): Promise<ValidateRes>;
  /** T-89 — OOV 라벨 매핑 후보(어휘·임베딩). 후보는 provisional. */
  oovCandidates(req: { label: string; k?: number }): Promise<Record<string, unknown>>;
  /** satisfy 응답은 **무변형 통과**. 재해석하면 CD-1 정규화가 두 곳에 생긴다. */
  satisfy(req: unknown): Promise<Record<string, unknown>>;
  kgSave(req: unknown): Promise<Record<string, unknown>>;
  /** CD-11 — A계층의 유일한 경로. 화이트리스트 명명 질의. */
  kgLookup(query: NamedQuery, params: Record<string, string>): Promise<LookupRes>;
  ragSearch(req: unknown): Promise<RagRes>;
  rulesCompile(categories?: string[]): Promise<Record<string, unknown>>;
  rulesDryRun(req: unknown): Promise<Record<string, unknown>>;
  reasonConsistency(req: unknown): Promise<Record<string, unknown>>;
  // CD-10 신설 — 조회·관리자 표면
  graph(q: GraphQuery): Promise<Record<string, unknown>>;
  dashboard(): Promise<Record<string, unknown>>;
  governanceConcepts(): Promise<Record<string, unknown>>;
  governanceCreate(req: unknown): Promise<Record<string, unknown>>;
  governanceDelete(id: string): Promise<Record<string, unknown>>;
  upperOntologyClasses(): Promise<Record<string, unknown>>;
  upperOntologyCreate(req: unknown): Promise<Record<string, unknown>>;
  upperOntologyImpact(req: unknown): Promise<Record<string, unknown>>;
  rules(): Promise<Record<string, unknown>>;
  ruleImpact(id: string): Promise<Record<string, unknown>>;
  // 프로젝트 (FR-3b·3c)
  createProject(req: unknown): Promise<Record<string, unknown>>;
  getProject(id: string): Promise<Record<string, unknown>>;
  setKnowledgeScope(id: string, req: unknown): Promise<Record<string, unknown>>;
  categories(): Promise<Record<string, unknown>>;
}

async function call<T>(path: string, init: RequestInit, traceId: string, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${config.knowledgeUrl}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", "X-Trace-Id": traceId, ...(init.headers ?? {}) },
    });
    const body = (await res.json()) as Record<string, unknown>;
    if (!res.ok) {
      // 지식서비스 에러 코드를 보존해 그대로 전파한다 (error_model.md §4).
      throw new AppError(
        (body.code as never) ?? "INTERNAL",
        (body.user_message as string) ?? "일시적인 오류입니다.",
        res.status,
        `knowledge ${path} → ${res.status}`,
      );
    }
    return body as T;
  } catch (err) {
    if (err instanceof AppError) throw err;
    throw new KnowledgeUnavailable(`${path}: ${err instanceof Error ? err.message : String(err)}`);
  } finally {
    clearTimeout(timer);
  }
}

function createHttpKnowledgeClient(traceId: string): KnowledgeClient {
  const { knowledgeMs, satisfyMs } = config.timeouts;
  const post = <T>(path: string, body: unknown, timeout: number = knowledgeMs) =>
    call<T>(path, { method: "POST", body: JSON.stringify(body) }, traceId, timeout);
  const get = <T>(path: string, timeout: number = knowledgeMs) =>
    call<T>(path, { method: "GET" }, traceId, timeout);
  const del = <T>(path: string, timeout: number = knowledgeMs) =>
    call<T>(path, { method: "DELETE" }, traceId, timeout);

  return {
    health: () => get("/health"),
    validateShacl: (req) => post("/validate/shacl", req),
    oovCandidates: (req) => post("/oov/candidates", req),
    satisfy: (req) => post("/satisfy", req, satisfyMs),
    kgSave: (req) => post("/kg/save", req),
    kgLookup: (query, params) => post("/kg/lookup", { query, params }),
    ragSearch: (req) => post("/rag/search", req),
    rulesCompile: (categories) => post("/rules/compile", { categories: categories ?? null }),
    rulesDryRun: (req) => post("/rules/dry-run", req),
    reasonConsistency: (req) => post("/reason/consistency", req),
    graph: (q) => {
      const params = new URLSearchParams();
      for (const [k, v] of Object.entries(q)) if (v !== undefined) params.set(k, String(v));
      return get(`/graph?${params.toString()}`);
    },
    dashboard: () => get("/dashboard"),
    governanceConcepts: () => get("/governance/concepts"),
    governanceCreate: (req) => post("/governance/concepts", req),
    governanceDelete: (id) => del(`/governance/concepts/${encodeURIComponent(id)}`),
    upperOntologyClasses: () => get("/upper-ontology/classes"),
    upperOntologyCreate: (req) => post("/upper-ontology/classes", req),
    upperOntologyImpact: (req) => post("/upper-ontology/impact", req),
    rules: () => get("/rules"),
    ruleImpact: (id) => get(`/rules/${encodeURIComponent(id)}/impact`),
    createProject: (req) => post("/projects", req),
    getProject: (id) => get(`/projects/${encodeURIComponent(id)}`),
    setKnowledgeScope: (id, req) => call("/projects/" + encodeURIComponent(id) + "/knowledge-scope", { method: "PUT", body: JSON.stringify(req) }, traceId, knowledgeMs),
    categories: () => get("/categories"),
  };
}

/**
 * 팩토리. `config.knowledgeMock` 이면 fixture 백엔드 mock, 아니면 실제 HTTP.
 * (환경변수 KNOWLEDGE_MOCK 로 전환 가능 — 병렬 규약.)
 */
export function createKnowledgeClient(traceId: string): KnowledgeClient {
  return config.knowledgeMock ? createKnowledgeMock(traceId) : createHttpKnowledgeClient(traceId);
}

export { createHttpKnowledgeClient };
