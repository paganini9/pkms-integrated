/**
 * T-51 — /extraction/stream (SSE) · /extraction/validate · /extraction/save (HITL 게이트).
 * SSE 순서: status* → (concept|relation)* → validation → done. error 는 어디서든 종료.
 * validation 은 지식서비스 /validate/shacl 결과다 (LLM 아님, 불변원칙 3).
 */
import { randomUUID } from "node:crypto";
import { Router, type Response } from "express";

import { AppError, GuardrailBlocked } from "../core/errors.js";
import { log } from "../core/trace.js";
import { parseOrThrow } from "../core/validate.js";
import { saveReqSchema, streamReqSchema, validateReqSchema } from "../schemas/requests.js";
import type { Concept, Relation } from "../services/ai/types.js";
import type { Violation } from "../services/knowledgeClient.js";
import { asyncHandler, type Deps } from "./deps.js";

/** Idempotency (interface_contracts.md §6): draft_id 기준 중복 저장 방지. 프로세스 메모리(재기동 시 소실). */
const savedDrafts = new Map<string, Record<string, unknown>>();

function sse(res: Response, event: string, data: unknown): void {
  res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

function errorBody(err: unknown, traceId: string) {
  if (err instanceof AppError) return err.toBody(traceId);
  return { code: "INTERNAL", user_message: "일시적인 오류입니다.", trace_id: traceId };
}

export function createExtractionRouter(deps: Deps): Router {
  const r = Router();

  // ── SSE 스트림 ──
  r.post("/stream", (req, res) => {
    const parsed = streamReqSchema.safeParse(req.body);
    if (!parsed.success) {
      // 헤더 전송 전이므로 일반 422 로 응답한다.
      res.status(422).json({
        code: "VALIDATION_ERROR",
        user_message: "입력값을 확인해 주세요.",
        trace_id: req.traceId,
        details: { field: parsed.error.issues[0]?.path.join(".") },
      });
      return;
    }
    const { text, project_id } = parsed.data;
    const threadId = parsed.data.thread_id ?? randomUUID();
    const draftId = randomUUID().replace(/-/g, "").slice(0, 12);

    res.status(200).set({
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    res.flushHeaders?.();

    void (async () => {
      const gateway = deps.makeGateway(req.traceId);
      const knowledge = deps.makeKnowledge(req.traceId);
      const concepts: Concept[] = [];
      const relations: Relation[] = [];
      try {
        for await (const ev of gateway.extract(text)) {
          if (ev.kind === "status") sse(res, "status", { stage: ev.stage, msg: ev.msg });
          else if (ev.kind === "concept") {
            concepts.push(ev.concept);
            sse(res, "concept", ev.concept);
          } else {
            relations.push(ev.relation);
            sse(res, "relation", ev.relation);
          }
        }
      } catch (err) {
        // 부분 결과(이미 보낸 concept/relation)는 유지하고 error 로 종료한다.
        log(req.traceId, "warn", `extraction stream error: ${String(err)}`);
        sse(res, "error", errorBody(err, req.traceId));
        res.end();
        return;
      }

      // 검증 단계 — 지식서비스가 판정한다.
      try {
        sse(res, "status", { stage: "validate", msg: "명세 검증 중" });
        const v = await knowledge.validateShacl({ concepts, relations, project_id: project_id ?? null });
        sse(res, "validation", { conforms: v.conforms, violations: v.violations });
      } catch (err) {
        sse(res, "error", errorBody(err, req.traceId));
        res.end();
        return;
      }

      sse(res, "done", { thread_id: threadId, draft_id: draftId, trace_id: req.traceId });
      res.end();
    })();
  });

  // ── 동기 검증 ──
  r.post(
    "/validate",
    asyncHandler(async (req, res) => {
      const body = parseOrThrow(validateReqSchema, req.body);
      const knowledge = deps.makeKnowledge(req.traceId);
      const v = await knowledge.validateShacl(body);
      res.json({ conforms: v.conforms, violations: v.violations, trace_id: req.traceId });
    }),
  );

  // ── HITL 게이트 저장 ──
  r.post(
    "/save",
    asyncHandler(async (req, res) => {
      const body = parseOrThrow(saveReqSchema, req.body);

      // (1) 미승인 → 409.
      if (body.approved !== true) {
        throw new GuardrailBlocked("save: approved!==true");
      }

      // (2) Idempotency — draft_id 재요청은 저장된 결과를 그대로 돌려준다.
      if (body.draft_id) {
        const cached = savedDrafts.get(body.draft_id);
        if (cached) {
          res.status(201).json({ ...cached, trace_id: req.traceId });
          return;
        }
      }

      const knowledge = deps.makeKnowledge(req.traceId);

      // (3) 서버측 재검증 — 클라이언트가 보낸 violations 는 신뢰하지 않는다(위조 방지).
      const recheck = await knowledge.validateShacl({
        concepts: body.concepts,
        relations: body.relations,
        project_id: body.project_id ?? null,
      });
      const hasBlocking = recheck.violations.some((vi: Violation) => vi.severity === "violation");
      if (hasBlocking) {
        throw new GuardrailBlocked(`save: server revalidation found ${recheck.violations.length} violation(s)`);
      }

      // (4) 저장 (트리플+벡터 원자적 — 지식서비스 책임).
      // D6: 지식서비스 SaveRequest.approved 는 Literal[True] 필수 → 반드시 실어 보낸다(다층 방어).
      //     draft_id 도 멱등 키로 함께 넘긴다(계약 §4.3 v1.3).
      const saved = await knowledge.kgSave({
        sentence_text: body.sentence_text,
        concepts: body.concepts,
        relations: body.relations,
        category: body.category,
        approved: true,
        ...(body.draft_id ? { draft_id: body.draft_id } : {}),
        project_id: body.project_id ?? null,
      });
      if (body.draft_id) savedDrafts.set(body.draft_id, saved);
      res.status(201).json({ ...saved, trace_id: req.traceId });
    }),
  );

  return r;
}

/** 테스트 격리용. */
export function _resetSavedDrafts(): void {
  savedDrafts.clear();
}
