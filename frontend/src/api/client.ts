/** BFF `/api/v1` 클라이언트. 프론트는 지식서비스를 직접 호출하지 않는다. */
import type { ApiError, GraphResponse, QaResponse, SatisfyResponse } from "../types/contracts";

const BASE = "/api/v1";

export class ApiCallError extends Error {
  constructor(public readonly body: ApiError) {
    // 기술 메시지 대신 다음 행동 안내를 보여준다 (기술설계 §7 에러 UX).
    super(body.user_message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await res.json();
  if (!res.ok) throw new ApiCallError(body as ApiError);
  return body as T;
}

export const api = {
  health: () => request<{ status: string; llm_provider: string }>("/health"),
  satisfy: (req: unknown) => request<SatisfyResponse>("/satisfy", { method: "POST", body: JSON.stringify(req) }),
  qa: (req: unknown) => request<QaResponse>("/qa", { method: "POST", body: JSON.stringify(req) }),
  graph: (params: Record<string, string>) => request<GraphResponse>(`/graph?${new URLSearchParams(params)}`),
};
