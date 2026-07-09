/**
 * PKMS BFF — 외부에 노출되는 유일한 표면 (`/api/v1`).
 *
 * 역할: 오케스트레이션 · AI Gateway(LLM 생성) · SSE · 지식서비스 클라이언트.
 * 하지 않는 일: RDF·SPARQL·SHACL·추론. 판정은 지식서비스가 한다.
 */
import cors from "cors";
import express from "express";

import { config } from "./core/config.js";
import { errorHandler } from "./core/errorHandler.js";
import { KnowledgeUnavailable } from "./core/errors.js";
import { log, traceMiddleware } from "./core/trace.js";
import { createKnowledgeClient } from "./services/knowledgeClient.js";

const app = express();
app.use(cors());
app.use(express.json({ limit: "1mb" }));
app.use(traceMiddleware);

const v1 = express.Router();

v1.get("/health", async (req, res) => {
  let knowledge: unknown = null;
  let status: "ok" | "degraded" = "ok";
  try {
    knowledge = await createKnowledgeClient(req.traceId).health();
  } catch (err) {
    // 지식서비스 도달 불가는 200 degraded 로 알린다 (프론트가 배너 표시).
    status = "degraded";
    knowledge = { status: "unavailable" };
    if (!(err instanceof KnowledgeUnavailable)) throw err;
  }
  res.json({
    status,
    llm_provider: config.aiMockMode ? "mock" : config.anthropicApiKey ? "claude" : "gemini",
    knowledge,
    trace_id: req.traceId,
  });
});

// ── Phase 2 에서 05 백엔드 Agent 가 채운다 (api_standard.md §4) ──
// v1.post("/extraction/stream", extractionStream);   // SSE
// v1.post("/extraction/validate", extractionValidate);
// v1.post("/extraction/save", extractionSave);       // HITL 게이트
// v1.post("/satisfy", satisfy);
// v1.post("/qa", qa);
// v1.get("/graph", graph);
// v1.use("/upper-ontology", requireAdmin, upperOntologyRouter);
// v1.use("/rules", requireAdmin, rulesRouter);
// v1.use("/governance", requireAdmin, governanceRouter);

app.use("/api/v1", v1);
app.use(errorHandler);

app.listen(config.port, () => {
  log("-", "info", `BFF 기동 :${config.port} — llm=${config.aiMockMode ? "mock" : "real"} knowledge=${config.knowledgeUrl}`);
});

export { app };
