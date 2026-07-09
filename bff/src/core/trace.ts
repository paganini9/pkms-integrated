/** trace_id 생성·전파 (CD-6) + 로깅. */
import { randomUUID } from "node:crypto";
import type { NextFunction, Request, Response } from "express";

import { maskSecrets } from "./config.js";

declare module "express-serve-static-core" {
  interface Request {
    traceId: string;
    role: "engineer" | "admin";
  }
}

export function traceMiddleware(req: Request, res: Response, next: NextFunction): void {
  req.traceId = (req.header("X-Trace-Id") ?? randomUUID().replace(/-/g, "").slice(0, 16)) as string;
  req.role = req.header("X-Role") === "admin" ? "admin" : "engineer"; // CD-5 Mock-Role
  res.setHeader("X-Trace-Id", req.traceId);
  next();
}

export function log(traceId: string, level: "info" | "warn" | "error", msg: string): void {
  const line = `${new Date().toISOString()} ${level.toUpperCase().padEnd(5)} [${traceId}] ${msg}`;
  console[level === "error" ? "error" : "log"](maskSecrets(line));
}
