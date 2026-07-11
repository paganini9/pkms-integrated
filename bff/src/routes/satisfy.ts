/**
 * T-52 — /satisfy. 지식서비스 응답을 **무변형 통과** (CD-1 정규화가 두 곳에 생기면 안 된다).
 * zod 로 형태만 검증하고 그대로 흘린다. trace_id 만 요청값으로 맞춘다(CD-6).
 * satisfies:null + pending_reason:"missing_required" (CD-8) 도 200 으로 나간다.
 */
import { Router } from "express";

import { parseOrThrow } from "../core/validate.js";
import { satisfyReqSchema } from "../schemas/requests.js";
import { asyncHandler, type Deps } from "./deps.js";
import { resolveCategories } from "./scope.js";

export function createSatisfyRouter(deps: Deps): Router {
  const r = Router();

  r.post(
    "/",
    asyncHandler(async (req, res) => {
      const body = parseOrThrow(satisfyReqSchema, req.body);
      const knowledge = deps.makeKnowledge(req.traceId);
      // D1(CD-4): 프로젝트 지식범위를 컴파일 필터로 넘긴다. 없으면 프로젝트 조회로 채운다.
      const categories = await resolveCategories(knowledge, body.project_id, body.categories);
      const result = await knowledge.satisfy({
        project_id: body.project_id,
        design: body.design,
        require: body.require ?? [], // D2: 내부 SatisfyRequest.require 는 null 을 거부(422). [] 로 보낸다.
        categories,
      });
      // 판정 필드(satisfies·violations·steps…)는 손대지 않는다. trace_id 만 맞춘다.
      res.status(200).json({ ...result, trace_id: req.traceId });
    }),
  );

  return r;
}
