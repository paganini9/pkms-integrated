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
import { log, traceMiddleware } from "./core/trace.js";
import { createV1Router } from "./routes/index.js";

export function createApp(): express.Express {
  const app = express();
  app.use(cors());
  app.use(express.json({ limit: "1mb" }));
  app.use(traceMiddleware);
  app.use("/api/v1", createV1Router());
  app.use(errorHandler);
  return app;
}

const app = createApp();

if (process.env.NODE_ENV !== "test") {
  app.listen(config.port, () => {
    log(
      "-",
      "info",
      `BFF 기동 :${config.port} — llm=${config.aiMockMode ? "mock" : "real"} knowledge=${config.knowledgeMock ? "mock" : config.knowledgeUrl}`,
    );
  });
}

export { app };
