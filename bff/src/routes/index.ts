/** /api/v1 라우터 조립. 테스트는 deps 를 주입해 gateway·knowledge 를 갈아끼운다. */
import { Router } from "express";

import { config } from "../core/config.js";
import { KnowledgeUnavailable } from "../core/errors.js";
import { requireAdmin } from "../core/errorHandler.js";
import { createGovernanceRouter, createRulesRouter, createUpperOntologyRouter } from "./admin.js";
import { asyncHandler, defaultDeps, type Deps } from "./deps.js";
import { createExtractionRouter } from "./extraction.js";
import { createMiscRouter } from "./misc.js";
import { createQaRouter } from "./qa.js";
import { createSatisfyRouter } from "./satisfy.js";

function llmProvider(): "mock" | "claude" | "gemini" {
  if (config.aiMockMode) return "mock";
  if (config.anthropicApiKey) return "claude";
  if (config.googleAiApiKey) return "gemini";
  return "mock";
}

export function createV1Router(deps: Deps = defaultDeps): Router {
  const v1 = Router();

  // /health — 역할 없음. 지식 도달 불가여도 200 degraded (500 아님).
  v1.get(
    "/health",
    asyncHandler(async (req, res) => {
      let knowledge: unknown = null;
      let status: "ok" | "degraded" = "ok";
      try {
        knowledge = await deps.makeKnowledge(req.traceId).health();
      } catch (err) {
        status = "degraded";
        knowledge = { status: "unavailable" };
        if (!(err instanceof KnowledgeUnavailable)) throw err;
      }
      res.json({ status, llm_provider: llmProvider(), knowledge, trace_id: req.traceId });
    }),
  );

  v1.use("/extraction", createExtractionRouter(deps));
  v1.use("/satisfy", createSatisfyRouter(deps));
  v1.use("/qa", createQaRouter(deps));
  v1.use("/", createMiscRouter(deps)); // /graph · /dashboard · /projects* · /categories

  // 관리자 표면 — 비관리자 403 FORBIDDEN (CD-5).
  v1.use("/upper-ontology", requireAdmin, createUpperOntologyRouter(deps));
  v1.use("/rules", requireAdmin, createRulesRouter(deps));
  v1.use("/governance", requireAdmin, createGovernanceRouter(deps));

  return v1;
}
