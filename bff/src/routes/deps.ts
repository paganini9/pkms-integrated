/** 라우트 의존성 — 테스트에서 gateway·knowledge 를 주입할 수 있게 팩토리로 둔다. */
import type { NextFunction, Request, RequestHandler, Response } from "express";

import { AIGateway, type GatewayTask } from "../services/ai/gateway.js";
import type { ProviderName } from "../services/ai/types.js";
import { createKnowledgeClient, type KnowledgeClient } from "../services/knowledgeClient.js";

export interface Deps {
  // T-90 providerName(명시) > 정책 task 기본(저작=claude / Q&A=solar) > 레거시 자동.
  makeGateway: (traceId: string, providerName?: ProviderName, task?: GatewayTask) => AIGateway;
  makeKnowledge: (traceId: string) => KnowledgeClient;
}

export const defaultDeps: Deps = {
  makeGateway: (traceId, providerName, task) =>
    new AIGateway(traceId, { ...(providerName ? { providerName } : {}), ...(task ? { task } : {}) }),
  makeKnowledge: (traceId) => createKnowledgeClient(traceId),
};

/** async 핸들러의 예외를 errorHandler 로 넘긴다 (express 4 는 자동 포착하지 않는다). */
export function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<unknown>,
): RequestHandler {
  return (req, res, next) => {
    fn(req, res, next).catch(next);
  };
}
