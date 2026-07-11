/** 응답 본문을 만드는 유일한 지점 (error_model.md §5). 핸들러 밖에서 에러 본문을 조립하지 않는다. */
import type { NextFunction, Request, Response } from "express";

import { AppError, Forbidden } from "./errors.js";
import { log } from "./trace.js";

export function errorHandler(err: unknown, req: Request, res: Response, _next: NextFunction): void {
  const traceId = req.traceId ?? "-";

  if (err instanceof AppError) {
    log(traceId, "warn", `${err.code}: ${err.internal ?? "-"}`);
    res.status(err.httpStatus).json(err.toBody(traceId));
    return;
  }

  log(traceId, "error", `UNHANDLED: ${err instanceof Error ? err.stack : String(err)}`);
  res.status(500).json({
    code: "INTERNAL",
    user_message: "일시적인 오류입니다.",
    trace_id: traceId,
  });
}

/** admin 전용 표면 게이트 (CD-5). */
export function requireAdmin(req: Request, _res: Response, next: NextFunction): void {
  if (req.role !== "admin") {
    next(new Forbidden(`role=${req.role}`));
    return;
  }
  next();
}
