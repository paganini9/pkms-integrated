/**
 * 실제 BFF `/api/v1` 클라이언트. VITE_USE_MOCK=false 일 때 사용.
 * 프론트는 지식서비스를 직접 호출하지 않는다 (내부 구조 비노출).
 */
import type {
  ApiError, GraphResponse, HealthResponse, QaResponse, SatisfyResponse,
  ValidateResponse, SaveResponse, RequirementsResponse, ProjectResponse,
} from "../types/contracts";
import {
  ApiCallError, type PkmsApi, type StreamHandlers, type StreamRequest,
  type StreamController, type ValidateRequest, type SaveRequest,
  type SatisfyRequest, type QaRequest, type RequirementsRequest, type CreateProjectRequest,
  type ABExtractRequest, type ABExtractResponse,
} from "./types";

const BASE = "/api/v1";

function role(): string {
  return localStorage.getItem("pkms_role") ?? "engineer";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Role": role(), ...(init?.headers ?? {}) },
    });
  } catch {
    // 네트워크 도달 실패 — 계약 형태의 에러로 정규화
    throw new ApiCallError({
      code: "KNOWLEDGE_UNAVAILABLE",
      user_message: "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
      trace_id: "n/a",
    });
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiCallError(body as ApiError);
  return body as T;
}

/** SSE 소비 (§5): fetch 스트림을 라인 파싱. 재연결·재시도는 하지 않는다. */
function extractionStream(req: StreamRequest, h: StreamHandlers): StreamController {
  const ctrl = new AbortController();
  (async () => {
    let res: Response;
    try {
      res = await fetch(`${BASE}/extraction/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Role": role() },
        body: JSON.stringify(req),
        signal: ctrl.signal,
      });
    } catch {
      h.onError?.({ code: "KNOWLEDGE_UNAVAILABLE", user_message: "서버에 연결할 수 없습니다. 다시 시도해 주세요.", trace_id: "n/a" });
      return;
    }
    if (!res.ok || !res.body) {
      const body = (await res.json().catch(() => null)) as ApiError | null;
      h.onError?.(body ?? { code: "INTERNAL", user_message: "일시적인 오류입니다. 다시 시도해 주세요.", trace_id: "n/a" });
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let evt = "";
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          const t = line.trim();
          if (t.startsWith("event:")) evt = t.slice(6).trim();
          else if (t.startsWith("data:")) {
            const data = JSON.parse(t.slice(5).trim());
            dispatch(evt, data, h);
          }
        }
      }
    } catch {
      // 스트림 끊김 — 자동 재시도 금지, 사용자에게 재시도 버튼 노출
      h.onError?.({ code: "INTERNAL", user_message: "스트리밍이 중단되었습니다. 다시 시도해 주세요.", trace_id: "n/a" });
    }
  })();
  return { cancel: () => ctrl.abort() };
}

function dispatch(evt: string, data: unknown, h: StreamHandlers) {
  switch (evt) {
    case "status": h.onStatus?.(data as never); break;
    case "concept": h.onConcept?.(data as never); break;
    case "relation": h.onRelation?.(data as never); break;
    case "validation": h.onValidation?.(data as never); break;
    case "done": h.onDone?.(data as never); break;
    case "error": h.onError?.(data as ApiError); break;
  }
}

export const realApi: PkmsApi = {
  health: () => request<HealthResponse>("/health"),
  extractionStream,
  extractionAB: (req: ABExtractRequest) =>
    request<ABExtractResponse>("/extraction/ab", { method: "POST", body: JSON.stringify(req) }),
  extractionValidate: (req: ValidateRequest) =>
    request<ValidateResponse>("/extraction/validate", { method: "POST", body: JSON.stringify(req) }),
  extractionSave: (req: SaveRequest) =>
    request<SaveResponse>("/extraction/save", { method: "POST", body: JSON.stringify(req) }),
  satisfy: (req: SatisfyRequest) =>
    request<SatisfyResponse>("/satisfy", { method: "POST", body: JSON.stringify(req) }),
  qa: (req: QaRequest) =>
    request<QaResponse>("/qa", { method: "POST", body: JSON.stringify(req) }),
  graph: (params: Record<string, string>) =>
    request<GraphResponse>(`/graph?${new URLSearchParams(params)}`),
  createProject: (req: CreateProjectRequest) =>
    request<ProjectResponse>("/projects", { method: "POST", body: JSON.stringify(req) }),
  parseRequirements: (projectId: string, req: RequirementsRequest) =>
    request<RequirementsResponse>(`/projects/${projectId}/requirements`, { method: "POST", body: JSON.stringify(req) }),
};
