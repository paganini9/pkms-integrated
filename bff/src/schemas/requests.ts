/**
 * 요청 스키마 (zod). 위반 → 422 VALIDATION_ERROR (api_standard §1).
 * CD-8: Design 의 수치·형상·환경은 선택(nullable). 필수는 material·vehicle 뿐.
 */
import { z } from "zod";

export const conceptTypeSchema = z.enum([
  "PartType", "Component", "Material", "VehicleType",
  "EnvCondition", "Symptom", "Behavior", "Attribute",
]);

export const predicateSchema = z.enum([
  "causes", "mitigates", "aggravates", "conditionedOn",
  "hasMaterial", "has_part", "mountedOn", "operatesIn",
]);

export const conceptSchema = z.object({
  label: z.string().min(1),
  type: conceptTypeSchema,
  iri: z.string().optional(),
  span: z.tuple([z.number(), z.number()]).optional(),
});

export const relationSchema = z.object({
  subject: z.string().min(1),
  predicate: predicateSchema,
  object: z.string().min(1),
  evidence: z.string().optional(),
  confidence: z.number().optional(),
});

// T-90 — 저작 추출 provider 선택. 미지정 시 설정 기본(solar).
export const providerSchema = z.enum(["solar", "claude", "gemini", "mock"]);

export const streamReqSchema = z.object({
  text: z.string().min(1).max(2000),
  thread_id: z.string().optional(),
  project_id: z.string().optional(),
  provider: providerSchema.optional(),
});

// A/B diff — 두 모델로 동시 추출(T-90). 기본 [solar, claude].
export const abExtractReqSchema = z.object({
  text: z.string().min(1).max(2000),
  providers: z.array(providerSchema).min(2).max(2).optional(),
});

// OOV 트리아지(T-89) — 매핑 후보 요청.
export const oovTriageSchema = z.object({
  label: z.string().min(1).max(100),
  sentence: z.string().max(2000).optional(),
  project_id: z.string().optional(),
  k: z.number().int().min(1).max(5).optional(),
});

export const validateReqSchema = z.object({
  concepts: z.array(conceptSchema),
  relations: z.array(relationSchema),
  project_id: z.string().optional(),
});

export const saveReqSchema = z.object({
  sentence_text: z.string().min(1),
  concepts: z.array(conceptSchema),
  relations: z.array(relationSchema),
  category: z.string().min(1),
  approved: z.boolean(),
  draft_id: z.string().optional(),
  project_id: z.string().optional(),
});

// CD-8 — material·vehicle 만 필수. 나머지는 선택(nullable).
export const designSchema = z.object({
  id: z.string().optional(),
  label: z.string().optional(),
  material: z.enum(["Rubber", "Silicone"]),
  vehicle: z.enum(["MidSizeSUV", "CompactSedan"]),
  length_mm: z.number().positive().nullable().optional(),
  spring_n: z.number().positive().nullable().optional(),
  arm_shape: z.enum(["simple", "complex"]).nullable().optional(),
  env: z.enum(["Winter"]).nullable().optional(),
});

export const satisfyReqSchema = z.object({
  project_id: z.string(),
  design: designSchema,
  require: z.array(z.string()).optional(),
  // 계약 외 편의: 카테고리를 직접 넘기면 그대로 컴파일 필터로 쓴다(없으면 프로젝트 범위).
  categories: z.array(z.string()).optional(),
});

export const qaReqSchema = z.object({
  question: z.string().min(1),
  mode: z.enum(["compare", "verified"]),
  project_id: z.string().optional(),
  thread_id: z.string().optional(),
});

export const graphQuerySchema = z.object({
  layer: z.enum(["M0", "M1", "M2"]).optional(),
  symptom: z.string().optional(),
  sentence: z.string().optional(),
  project_id: z.string().optional(),
  limit: z.coerce.number().int().positive().max(5000).optional(),
});

export const createProjectSchema = z.object({
  name: z.string().min(1),
  target_vehicle: z.string().optional(),
  target_env: z.string().optional(),
  knowledge_categories: z.array(z.string()).optional(),
});

export const knowledgeScopeSchema = z.object({
  categories: z.array(z.string()),
});

export const requirementsReqSchema = z.object({
  text: z.string().min(1),
});

export const approvedChangeSchema = z.object({
  approved: z.boolean().optional(),
}).passthrough();
