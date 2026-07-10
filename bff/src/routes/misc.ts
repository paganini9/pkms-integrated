/**
 * T-54(조회) + 프로젝트/카테고리 — /graph · /dashboard · /projects* · /categories.
 * BFF 는 역할 게이트 없는 engineer 표면. 무변형 통과 + trace_id.
 */
import { Router } from "express";

import { NotFound } from "../core/errors.js";
import { parseOrThrow } from "../core/validate.js";
import {
  createProjectSchema, graphQuerySchema, knowledgeScopeSchema, requirementsReqSchema,
} from "../schemas/requests.js";
import { asyncHandler, type Deps } from "./deps.js";

// 알려진 증상 → RB 매핑 (RB 파싱의 존재 검증).
const KNOWN_SYMPTOM: Record<string, { id: string; iri: string }> = {
  Noise: { id: "RB_Winter", iri: "http://ex.org/eng#RB_Winter" },
  TipChatter: { id: "RB_NoChatter", iri: "http://ex.org/eng#RB_NoChatter" },
};

export function createMiscRouter(deps: Deps): Router {
  const r = Router();

  r.get(
    "/graph",
    asyncHandler(async (req, res) => {
      const q = parseOrThrow(graphQuerySchema, req.query);
      const kn = deps.makeKnowledge(req.traceId);
      const g = await kn.graph(q);
      res.status(200).json({ ...g, trace_id: req.traceId });
    }),
  );

  r.get(
    "/dashboard",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      const d = await kn.dashboard();
      res.status(200).json({ ...d, trace_id: req.traceId });
    }),
  );

  r.get(
    "/categories",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      const c = await kn.categories();
      res.status(200).json({ ...c, trace_id: req.traceId });
    }),
  );

  r.post(
    "/projects",
    asyncHandler(async (req, res) => {
      const body = parseOrThrow(createProjectSchema, req.body);
      const kn = deps.makeKnowledge(req.traceId);
      const p = await kn.createProject(body);
      res.status(201).json({ ...p, trace_id: req.traceId });
    }),
  );

  r.get(
    "/projects/:id",
    asyncHandler(async (req, res) => {
      const kn = deps.makeKnowledge(req.traceId);
      const p = await kn.getProject(req.params.id!);
      if (!p) throw new NotFound(`project ${req.params.id!}`);
      res.status(200).json({ ...p, trace_id: req.traceId });
    }),
  );

  r.put(
    "/projects/:id/knowledge-scope",
    asyncHandler(async (req, res) => {
      const body = parseOrThrow(knowledgeScopeSchema, req.body);
      const kn = deps.makeKnowledge(req.traceId);
      const s = await kn.setKnowledgeScope(req.params.id!, body);
      res.status(200).json({ ...s, trace_id: req.traceId });
    }),
  );

  r.post(
    "/projects/:id/requirements",
    asyncHandler(async (req, res) => {
      const body = parseOrThrow(requirementsReqSchema, req.body);
      const gw = deps.makeGateway(req.traceId);
      const drafts = await gw.parseRequirements(body.text); // LLM 생성
      const requirements: Array<Record<string, unknown>> = [];
      const unknown_symptoms: string[] = [];
      for (const d of drafts) {
        const known = KNOWN_SYMPTOM[d.forbids_symptom];
        if (known) requirements.push({ id: known.id, iri: known.iri, label: d.label, forbids_symptom: d.forbids_symptom });
        else unknown_symptoms.push(d.forbids_symptom);
      }
      res.status(201).json({ requirements, unknown_symptoms, trace_id: req.traceId });
    }),
  );

  return r;
}
