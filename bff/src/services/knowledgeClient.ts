/**
 * 지식서비스 클라이언트 — BFF 가 지식에 접근하는 **유일한 경로**.
 * 여기서 RDF/SPARQL/SHACL 문자열을 만들지 않는다. 지식서비스가 판정하고, BFF 는 통과시킨다.
 *
 * Phase 1 스켈레톤: 각 메서드는 05 백엔드 Agent 가 채운다.
 * 계약: `_coordination/contracts/interface_contracts.md` §1
 */
import { config } from "../core/config.js";
import { AppError, KnowledgeUnavailable } from "../core/errors.js";

export interface KnowledgeClient {
  health(): Promise<unknown>;
  validateShacl(req: unknown): Promise<unknown>;
  /** satisfy 응답은 **무변형 통과**. 재해석하면 CD-1 정규화가 두 곳에 생긴다. */
  satisfy(req: unknown): Promise<unknown>;
  kgSave(req: unknown): Promise<unknown>;
  sparql(query: string): Promise<unknown>;
  ragSearch(req: unknown): Promise<unknown>;
  rulesCompile(categories?: string[]): Promise<unknown>;
  rulesDryRun(req: unknown): Promise<unknown>;
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

export function createKnowledgeClient(traceId: string): KnowledgeClient {
  const { knowledgeMs, satisfyMs } = config.timeouts;
  const post = (path: string, body: unknown, timeout: number = knowledgeMs) =>
    call<unknown>(path, { method: "POST", body: JSON.stringify(body) }, traceId, timeout);

  return {
    health: () => call("/health", { method: "GET" }, traceId, knowledgeMs),
    validateShacl: (req) => post("/validate/shacl", req),
    satisfy: (req) => post("/satisfy", req, satisfyMs),
    kgSave: (req) => post("/kg/save", req),
    sparql: (query) => post("/sparql", { query }),
    ragSearch: (req) => post("/rag/search", req),
    rulesCompile: (categories) => post("/rules/compile", { categories: categories ?? null }),
    rulesDryRun: (req) => post("/rules/dry-run", req),
  };
}
