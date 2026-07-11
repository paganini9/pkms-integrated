/** 테스트 유틸 — 임시 포트로 앱을 띄우고 HTTP 로 두드린다. SSE 파서 포함. */
import type { AddressInfo } from "node:net";
import cors from "cors";
import express, { type Express } from "express";
import { Agent, fetch } from "undici";

import { errorHandler } from "../src/core/errorHandler.js";
import { traceMiddleware } from "../src/core/trace.js";
import { createV1Router } from "../src/routes/index.js";
import type { Deps } from "../src/routes/deps.js";

/** deps 를 주입해 앱을 만든다(테스트용). */
export function appFor(deps?: Deps): Express {
  const app = express();
  app.use(cors());
  app.use(express.json({ limit: "1mb" }));
  app.use(traceMiddleware);
  app.use("/api/v1", createV1Router(deps));
  app.use(errorHandler);
  return app;
}

/**
 * 서버마다 전용 커넥션 풀을 쓴다 — 전역 fetch 의 공유 keep-alive 풀을 테스트 간에 물려주지 않는다.
 * 풀을 서버 수명에 묶으면 오리진(`127.0.0.1:PORT`) 캐시가 다음 서버로 샐 여지가 없다.
 *
 * NOTE: Phase 2 통합 중 이 스위트에서 산발적 실패를 2회 관측했다(서로 다른 파일의 서로 다른 테스트).
 * 출력을 보존하지 못했고 이후 37회 재현에 실패했다. **소켓 재사용이 원인이라는 증거는 없다** —
 * 직접 재현 실험에서 반증되었다(`closeAllConnections()` 가 소켓을 정리한다).
 * 이 격리는 공유 상태를 하나 줄이는 위생 조치이지, 그 실패의 검증된 수정이 아니다.
 * 재발 시 전체 출력을 반드시 보존할 것 — `integration_log.md#G2` 미결 항목.
 */
let dispatcher: Agent | undefined;

export async function withServer<T>(app: Express, fn: (base: string) => Promise<T>): Promise<T> {
  const server = app.listen(0);
  await new Promise<void>((r) => server.once("listening", () => r()));
  const port = (server.address() as AddressInfo).port;
  dispatcher = new Agent({ keepAliveTimeout: 1, keepAliveMaxTimeout: 1, pipelining: 0 });
  try {
    return await fn(`http://127.0.0.1:${port}`);
  } finally {
    await dispatcher.close();
    dispatcher = undefined;
    await new Promise<void>((r) => {
      server.close(() => r());
      (server as { closeAllConnections?: () => void }).closeAllConnections?.();
    });
  }
}

/** withServer 가 연 풀. 없으면 테스트가 서버 밖에서 fetch 하려 한 것이다. */
function pool(): Agent {
  if (!dispatcher) throw new Error("withServer() 바깥에서 HTTP 호출");
  return dispatcher;
}

export interface SseEvent {
  event: string;
  data: Record<string, unknown>;
}

/** SSE 응답을 끝까지 읽어 이벤트 배열로 반환한다. */
export async function readSse(base: string, path: string, body: unknown): Promise<SseEvent[]> {
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    dispatcher: pool(),
  });
  const text = await res.text();
  const events: SseEvent[] = [];
  for (const block of text.split("\n\n")) {
    const lines = block.split("\n");
    let event = "";
    let data = "";
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data = line.slice(5).trim();
    }
    if (event) events.push({ event, data: data ? JSON.parse(data) : {} });
  }
  return events;
}

export async function postJson(base: string, path: string, body: unknown, headers: Record<string, string> = {}) {
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
    dispatcher: pool(),
  });
  return { status: res.status, body: (await res.json()) as Record<string, unknown>, headers: res.headers };
}

export async function getJson(base: string, path: string, headers: Record<string, string> = {}) {
  const res = await fetch(`${base}${path}`, { headers, dispatcher: pool() });
  return { status: res.status, body: (await res.json()) as Record<string, unknown>, headers: res.headers };
}

export async function delJson(base: string, path: string, headers: Record<string, string> = {}) {
  const res = await fetch(`${base}${path}`, { method: "DELETE", headers, dispatcher: pool() });
  return { status: res.status, body: (await res.json()) as Record<string, unknown> };
}
