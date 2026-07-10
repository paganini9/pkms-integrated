/**
 * T-53 — /qa. A/B/C 라우팅 + 환각비교.
 * A: kgLookup(명명 질의, CD-11) · B: satisfy · C: rag/search → verified hit 만 근거(CD-9).
 * 분류: gateway.classify(LLM structured output) + 키워드 폴백.
 * mode:"compare" → 무근거 LLM 단독 답변을 **병렬 호출** + 대조기 comparison. verified → 둘 다 null.
 *
 * G2 수정 이력:
 *  D1 — B계층도 프로젝트 지식범위를 컴파일 필터로 넘긴다(CD-4).
 *  D2 — 내부 satisfy 는 require=null 을 거부 → [] 로 보낸다.
 *  D3 — A계층 답변은 lookup.rows 의 결정론 수치로 조립한다.
 *  D5 — 시드 문장 텍스트를 하드코딩하지 않는다(kgLookup 에서 받는다).
 *  CD-13(v1.4) — **가드레일은 라우팅보다 앞. 전 계층 fail-closed. 입력을 지어내지 않는다.**
 *    (1) 접지를 `/qa` 진입 직후 실행 — 인식 개념 0 → 계층 무관 insufficient.
 *    (2) A: 화이트리스트 미매칭 → 폴백 금지 → insufficient.
 *        B: material·vehicle 못 얻으면 날조 금지 → 판정 보류(insufficient, sources[]).
 *        C: 미지 개념 1건이라도 → insufficient(가장 보수적).
 *    (3) insufficient → sources 는 반드시 [].
 */
import { Router } from "express";

import { parseOrThrow } from "../core/validate.js";
import { qaReqSchema } from "../schemas/requests.js";
import type { AIGateway } from "../services/ai/gateway.js";
import type { Concept, Relation, Source } from "../services/ai/types.js";
import type { KnowledgeClient, NamedQuery } from "../services/knowledgeClient.js";
import { asyncHandler, type Deps } from "./deps.js";
import { resolveCategories } from "./scope.js";

const NO_EVIDENCE =
  "명세 근거 없음 — 이 질문은 현재 지식베이스(와이퍼 블레이드 도메인)의 검증된 규칙으로 답할 수 없습니다. 억지로 답을 만들지 않습니다. 해당 지식을 추가하려면 지식 입력 화면을 이용해 주세요.";

const PENDING_DESIGN =
  "판정 보류 — 질문에서 설계를 식별할 최소 정보(재질·차종)를 얻지 못했습니다. 재질(고무/실리콘)과 차종(중형 SUV/소형 세단)을 지정해 주세요. 기본값을 지어내 판정하지 않습니다.";

const VEHICLE_KO: Record<string, string> = { MidSizeSUV: "중형 SUV", CompactSedan: "소형 세단" };

type Determinism = "sparql" | "satisfy" | "rag";

interface QaResult {
  verified_answer: { text: string; determinism: Determinism; sources: Source[] };
  insufficient: boolean;
  contradicted: boolean; // 검증 판정이 위반(불가)이면 true — 대조기 입력
}

function insufficient(det: Determinism, text = NO_EVIDENCE): QaResult {
  return { verified_answer: { text, determinism: det, sources: [] }, insufficient: true, contradicted: false };
}

function layerDeterminism(layer: "A" | "B" | "C"): Determinism {
  return layer === "A" ? "sparql" : layer === "B" ? "satisfy" : "rag";
}

// ── CD-13(1): 접지 — 라우팅보다 먼저 ────────────────────────────────────────
interface Grounding {
  concepts: Concept[];
  recognized: Concept[]; // unknown_concept 로 안 걸린 개념
  hasUnknown: boolean; // unknown_concept 가 1건이라도 있었는가 (CD-13 C계층 게이트)
}

async function groundQuestion(question: string, kn: KnowledgeClient, gw: AIGateway): Promise<Grounding> {
  const concepts: Concept[] = [];
  const relations: Relation[] = [];
  for await (const ev of gw.extract(question)) {
    if (ev.kind === "concept") concepts.push(ev.concept);
    else if (ev.kind === "relation") relations.push(ev.relation);
  }
  if (concepts.length === 0) return { concepts, recognized: [], hasUnknown: false };
  // 지식서비스가 접지 판정(불변원칙 3 — BFF 는 판정하지 않는다).
  const val = await kn.validateShacl({ concepts, relations });
  const unknown = new Set(val.violations.filter((v) => v.code === "unknown_concept").map((v) => v.offender));
  const recognized = concepts.filter((c) => !unknown.has(c.label));
  return { concepts, recognized, hasUnknown: unknown.size > 0 };
}

// ── A: 화이트리스트 명명 질의. 매칭 실패 → null (폴백 금지) ──────────────────
function mapNamedQuery(question: string): { query: NamedQuery; params: Record<string, string> } | null {
  if (/안전/.test(question) && /길이/.test(question)) {
    const vehicle = /세단/.test(question) ? "CompactSedan" : "MidSizeSUV";
    return { query: "max_safe_length", params: { vehicle } };
  }
  // 증상→원인: 증상어 + 원인/규칙 의도가 명시된 경우에만.
  if (/(원인|왜|유발|규칙|일으키)/.test(question)) {
    if (/떨림|채터/.test(question)) return { query: "symptom_causes", params: { symptom: "TipChatter" } };
    if (/소음/.test(question)) return { query: "symptom_causes", params: { symptom: "Noise" } };
  }
  return null; // 기본 질의 없음 — 지어내지 않는다.
}

function assembleAnswerA(query: NamedQuery, rows: Array<Record<string, unknown>>, sources: Source[]): string {
  if (query === "max_safe_length" && rows[0]) {
    const row = rows[0];
    const veh = VEHICLE_KO[String(row.vehicle)] ?? String(row.vehicle);
    const max = row.max_safe_mm;
    const cite = sources[0]?.text ? ` (근거 ${sources[0].sentence}: ${sources[0].text})` : "";
    return `${veh}의 블레이드 안전 길이는 ${max}mm 이하입니다. ${max}mm 를 초과하면 규격을 벗어납니다.${cite}`;
  }
  const texts = sources.map((s) => s.text).filter((t): t is string => Boolean(t));
  return texts.length ? texts.join(" ") : `조회 결과 ${rows.length}건.`;
}

// ── B: 질문에서 설계를 **읽기만** 한다. 없는 값은 만들지 않는다 ────────────────
interface PartialDesign {
  material?: "Rubber" | "Silicone";
  vehicle?: "MidSizeSUV" | "CompactSedan";
  length_mm?: number;
  spring_n?: number;
  arm_shape?: "simple" | "complex";
  env?: "Winter";
}

function parseDesign(question: string): PartialDesign {
  const d: PartialDesign = {};
  if (/실리콘/.test(question)) d.material = "Silicone";
  else if (/고무/.test(question)) d.material = "Rubber";
  if (/세단/.test(question)) d.vehicle = "CompactSedan";
  else if (/SUV/i.test(question)) d.vehicle = "MidSizeSUV";
  const len = question.match(/(\d{3,4})\s*mm/);
  if (len) d.length_mm = Number(len[1]);
  const spring = question.match(/(\d+)\s*N\b/i);
  if (spring) d.spring_n = Number(spring[1]);
  if (/복잡|complex/i.test(question)) d.arm_shape = "complex";
  else if (/단순|simple/i.test(question)) d.arm_shape = "simple";
  if (/겨울/.test(question)) d.env = "Winter";
  return d;
}

function symptomsFrom(sat: Record<string, unknown>): string[] {
  const out = new Set<string>();
  for (const st of (sat.steps as Array<Record<string, unknown>>) ?? []) {
    if (st.stage === "symptom_free") {
      for (const ex of (st.exhibited as Array<{ symptom?: string }>) ?? []) if (ex.symptom) out.add(ex.symptom);
    }
  }
  for (const vr of (sat.violated_requirements as Array<{ forbids?: string }>) ?? []) if (vr.forbids) out.add(vr.forbids);
  return [...out];
}

/** D5 — B계층 근거를 지식서비스에서 받는다: violation 문장 텍스트 + 유발 규칙 id. */
async function buildSatisfySources(sat: Record<string, unknown>, kn: KnowledgeClient): Promise<Source[]> {
  const codes = (sat.violations as string[]) ?? [];
  const symptoms = symptomsFrom(sat);
  const textByCode: Record<string, string> = {};
  const ruleSources: Source[] = [];
  const seenRule = new Set<string>();
  for (const sym of symptoms) {
    let lk;
    try {
      lk = await kn.kgLookup("symptom_causes", { symptom: sym });
    } catch {
      continue;
    }
    for (const s of lk.sources) if (s.sentence && s.text) textByCode[s.sentence] = s.text;
    for (const row of lk.rows) {
      const rule = row.rule as string | undefined;
      if (rule && !seenRule.has(rule)) {
        seenRule.add(rule);
        ruleSources.push({ rule, iri: `http://ex.org/domain#${rule}` });
      }
    }
  }
  const sentenceSources: Source[] = [];
  const seenCode = new Set<string>();
  for (const c of codes) {
    if (seenCode.has(c)) continue;
    seenCode.add(c);
    const s: Source = { sentence: c, iri: `http://ex.org/domain#${c}` };
    if (textByCode[c]) s.text = textByCode[c];
    sentenceSources.push(s);
  }
  return [...sentenceSources, ...ruleSources];
}

// ── 계층 처리 ────────────────────────────────────────────────────────────
async function runLayerA(question: string, kn: KnowledgeClient): Promise<QaResult> {
  const m = mapNamedQuery(question);
  if (!m) return insufficient("sparql"); // CD-13: 폴백 금지
  const lookup = await kn.kgLookup(m.query, m.params);
  if (lookup.rows.length === 0) return insufficient("sparql");
  const sources = lookup.sources as Source[];
  return {
    verified_answer: { text: assembleAnswerA(m.query, lookup.rows, sources), determinism: "sparql", sources },
    insufficient: false,
    contradicted: false,
  };
}

/** CD-14: satisfy 판정 보류 사유를 결정론 문자열로. 지식서비스의 pending_reason·경고를 그대로 쓴다(재해석 금지). */
function pendingText(sat: Record<string, unknown>): string {
  const reason = String(sat.pending_reason ?? "missing_required");
  const missing = new Set<string>();
  for (const st of (sat.steps as Array<Record<string, unknown>>) ?? []) {
    for (const w of (st.warnings as Array<{ offender?: string }>) ?? []) if (w.offender) missing.add(w.offender);
  }
  const detail = missing.size > 0 ? ` 누락된 값: ${[...missing].join(", ")}.` : "";
  return `판정 보류 — 설계 수치가 부족해 확정 판정을 내릴 수 없습니다 (사유: ${reason}).${detail} 값을 채우면 확정 판정이 나옵니다.`;
}

async function runLayerB(
  question: string,
  projectId: string | undefined,
  kn: KnowledgeClient,
  gw: AIGateway,
): Promise<QaResult> {
  const d = parseDesign(question);
  // CD-13: 재질·차종을 못 얻으면 날조하지 않고 판정 보류한다.
  if (!d.material || !d.vehicle) return insufficient("satisfy", PENDING_DESIGN);
  let categories: string[] | null = null;
  try {
    categories = await resolveCategories(kn, projectId, undefined);
  } catch {
    categories = null;
  }
  const design: Record<string, unknown> = { material: d.material, vehicle: d.vehicle };
  if (d.length_mm !== undefined) design.length_mm = d.length_mm;
  if (d.spring_n !== undefined) design.spring_n = d.spring_n;
  if (d.arm_shape !== undefined) design.arm_shape = d.arm_shape;
  if (d.env !== undefined) design.env = d.env;
  const sat = await kn.satisfy({ project_id: projectId ?? null, design, require: [], categories });

  // CD-14: 판정 보류(satisfies===null) → LLM 을 부르지 않는다. 결정론 문자열 + insufficient.
  if (sat.satisfies === null) return insufficient("satisfy", pendingText(sat));

  const sources = await buildSatisfySources(sat, kn);
  const contradicted = sat.satisfies === false;
  // CD-14: sources 가 비면(만족·위반 없음) LLM 이 생성하지 않는다. 결정론 요약만.
  const text =
    sources.length > 0
      ? await gw.answer(question, sources)
      : `판정: 만족 — 적용 지식범위 내에서 위반이 없습니다.`;
  return { verified_answer: { text, determinism: "satisfy", sources }, insufficient: false, contradicted };
}

async function runLayerC(
  question: string,
  projectId: string | undefined,
  grounding: Grounding,
  kn: KnowledgeClient,
  gw: AIGateway,
): Promise<QaResult> {
  // CD-13 C계층: 미지 개념이 1건이라도 있으면 근거를 붙이지 않는다(가장 보수적).
  if (grounding.hasUnknown) return insufficient("rag");
  const rag = await kn.ragSearch({ query: question, k: 6, project_id: projectId ?? null });
  const verified = rag.hits.filter((h) => h.verified);
  if (verified.length === 0) return insufficient("rag"); // CD-9
  const sources: Source[] = verified.map((h) => ({ sentence: h.sentence, iri: h.iri, text: h.text }));
  const text = await gw.answer(question, sources);
  return { verified_answer: { text, determinism: "rag", sources }, insufficient: false, contradicted: false };
}

function computeComparison(res: QaResult, llmText: string) {
  const evidence = res.verified_answer.sources.map((s) => s.sentence).filter((x): x is string => Boolean(x));
  if (res.insufficient) {
    return {
      mismatches: [{ claim: llmText.slice(0, 40), verdict: "검증 불가 — 명세 근거 없음", evidence: [] as string[] }],
      violation_rate: 0.0,
      agreement_rate: 0.0,
    };
  }
  if (res.contradicted) {
    return {
      mismatches: [{ claim: "LLM 단독 답변", verdict: "위반 — 검증 판정과 불일치", evidence }],
      violation_rate: 1.0,
      agreement_rate: 0.0,
    };
  }
  return { mismatches: [] as Array<{ claim: string; verdict: string; evidence: string[] }>, violation_rate: 0.0, agreement_rate: 1.0 };
}

export function createQaRouter(deps: Deps): Router {
  const r = Router();

  r.post(
    "/",
    asyncHandler(async (req, res) => {
      const body = parseOrThrow(qaReqSchema, req.body);
      const gw = deps.makeGateway(req.traceId);
      const kn = deps.makeKnowledge(req.traceId);

      // 환각비교: 무근거 LLM 단독 답변을 병렬로 시작한다. (CD-14: verified_answer 와 **다른 함수**.)
      const llmPromise = body.mode === "compare" ? gw.llmOnlyAnswer(body.question) : null;

      // CD-13: 접지를 라우팅보다 **먼저**. 분류는 계층 라벨용.
      const grounding = await groundQuestion(body.question, kn, gw);
      const layer = await gw.classify(body.question);

      let result: QaResult;
      if (grounding.recognized.length === 0) {
        // 인식 개념 0 → 계층과 무관하게 근거 없음(전 계층 fail-closed).
        result = insufficient(layerDeterminism(layer));
      } else if (layer === "A") {
        result = await runLayerA(body.question, kn);
      } else if (layer === "B") {
        result = await runLayerB(body.question, body.project_id, kn, gw);
      } else {
        result = await runLayerC(body.question, body.project_id, grounding, kn, gw);
      }

      // CD-13(3): insufficient 면 sources 는 반드시 [].
      if (result.insufficient) result.verified_answer.sources = [];

      let llm_answer: { text: string; model: string } | null = null;
      let comparison: ReturnType<typeof computeComparison> | null = null;
      if (llmPromise) {
        const llmText = await llmPromise;
        llm_answer = { text: llmText, model: gw.providerName() };
        comparison = computeComparison(result, llmText);
      }

      res.status(200).json({
        layer,
        verified_answer: result.verified_answer,
        llm_answer,
        comparison,
        insufficient_evidence: result.insufficient,
        trace_id: req.traceId,
      });
    }),
  );

  return r;
}
