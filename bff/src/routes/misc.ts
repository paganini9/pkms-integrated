/**
 * T-54(조회) + 프로젝트/카테고리 — /graph · /dashboard · /projects* · /categories.
 * BFF 는 역할 게이트 없는 engineer 표면. 무변형 통과 + trace_id.
 */
import { Router } from "express";

import { NotFound } from "../core/errors.js";
import { parseOrThrow } from "../core/validate.js";
import {
  createProjectSchema, graphQuerySchema, knowledgeScopeSchema, oovTriageSchema, requirementsReqSchema,
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

  // ── OOV 트리아지 (T-89) — 매핑 후보 + provenance + 관리자 제안 스텁 ──
  // 후보는 provisional: 접지에 쓰이지 않는다(fail-closed 불변). 승인은 거버넌스(T-85 오버레이) 경유.
  r.post(
    "/oov/triage",
    asyncHandler(async (req, res) => {
      const body = parseOrThrow(oovTriageSchema, req.body);
      const kn = deps.makeKnowledge(req.traceId);
      const cand = (await kn.oovCandidates({ label: body.label, k: body.k ?? 3 })) as {
        candidates?: unknown[]; in_domain?: boolean; provisional?: boolean;
      };
      const candidates = cand.candidates ?? [];
      res.status(200).json({
        label: body.label,
        in_domain: cand.in_domain ?? false,
        provisional: cand.provisional ?? true,
        candidates,
        // provenance(어디서 왔나) — 편입 검토·반복신호의 근거.
        provenance: { sentence: body.sentence ?? null, project_id: body.project_id ?? null },
        // 5분류 트리아지 힌트: 후보 있으면 어휘변이(altLabel 제안), 없으면 범위 밖(정당한 거부).
        triage: candidates.length > 0 ? "synonym_variant" : "out_of_scope",
        admin_proposal: { status: "stub", action: candidates.length > 0 ? "altLabel 편입 제안" : "제안 없음(범위 밖)" },
        clarification: candidates.length === 0 ? "이 용어는 와이퍼 도메인 밖입니다. 다른 표현이면 바꿔 주세요." : null,
        trace_id: req.traceId,
      });
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
      const gw = deps.makeGateway(req.traceId, undefined, "authoring"); // RB 파싱(구조화) — 기본 claude
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
