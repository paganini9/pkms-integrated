/**
 * T-54(관리자 표면) — /upper-ontology/* · /rules/* · /governance/*.
 * 역할 게이트(CD-5)는 index 에서 requireAdmin 으로 건다. 여기선 HITL + 무변형 통과.
 * consistency 는 신설 아님 → 내부 /reason/consistency 로 매핑(CD-10).
 * builtin 삭제 400 BUILTIN_LOCKED 은 지식서비스가 판정, BFF 통과 (AC-8).
 */
import { Router } from "express";

import { GuardrailBlocked } from "../core/errors.js";
import { parseOrThrow } from "../core/validate.js";
import { approvedChangeSchema } from "../schemas/requests.js";
import { asyncHandler, type Deps } from "./deps.js";

export function createUpperOntologyRouter(deps: Deps): Router {
  const r = Router();

  r.get(
    "/classes",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      res.status(200).json({ ...(await kn.upperOntologyClasses()), trace_id: req.traceId });
    }),
  );

  r.post(
    "/classes",
    asyncHandler(async (req, res) => {
      const body = parseOrThrow(approvedChangeSchema, req.body);
      if (body.approved !== true) throw new GuardrailBlocked("upper-ontology save: approved!==true");
      const kn = deps.makeKnowledge(req.traceId);
      res.status(200).json({ ...(await kn.upperOntologyCreate(body)), trace_id: req.traceId });
    }),
  );

  // 신설하지 않는다 — 기존 /reason/consistency 로 매핑.
  r.post(
    "/consistency",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      res.status(200).json({ ...(await kn.reasonConsistency(req.body ?? {})), trace_id: req.traceId });
    }),
  );

  r.post(
    "/impact",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      res.status(200).json({ ...(await kn.upperOntologyImpact(req.body ?? {})), trace_id: req.traceId });
    }),
  );

  return r;
}

export function createRulesRouter(deps: Deps): Router {
  const r = Router();

  r.get(
    "/",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      res.status(200).json({ ...(await kn.rules()), trace_id: req.traceId });
    }),
  );

  r.post(
    "/dry-run",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      res.status(200).json({ ...(await kn.rulesDryRun(req.body ?? {})), trace_id: req.traceId });
    }),
  );

  r.get(
    "/:id/impact",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      res.status(200).json({ ...(await kn.ruleImpact(req.params.id!)), trace_id: req.traceId });
    }),
  );

  return r;
}

export function createGovernanceRouter(deps: Deps): Router {
  const r = Router();

  r.get(
    "/concepts",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      res.status(200).json({ ...(await kn.governanceConcepts()), trace_id: req.traceId });
    }),
  );

  r.post(
    "/concepts",
    asyncHandler(async (req, res) => {
      const body = parseOrThrow(approvedChangeSchema, req.body);
      if (body.approved !== true) throw new GuardrailBlocked("governance create: approved!==true");
      const kn = deps.makeKnowledge(req.traceId);
      res.status(201).json({ ...(await kn.governanceCreate(body)), trace_id: req.traceId });
    }),
  );

  r.delete(
    "/concepts/:id",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      // builtin 삭제 → 지식서비스가 400 BUILTIN_LOCKED 판정, BFF 는 전파.
      const out = await kn.governanceDelete(req.params.id!);
      res.status(200).json({ ...out, trace_id: req.traceId });
    }),
  );

  return r;
}
