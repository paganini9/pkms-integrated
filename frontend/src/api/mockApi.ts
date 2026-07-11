/**
 * Mock API — `contracts/mocks/*.json` fixture 를 API 경계에서 그대로 서빙한다.
 * 05 백엔드가 BFF 를 구현 중이므로 프론트는 이 mock 으로 선행한다(병렬 규약).
 * VITE_USE_MOCK 로 realApi 와 교체된다. fixture 는 컴포넌트가 아니라 여기(경계)에서만 쓴다.
 */
import type {
  GraphResponse, HealthResponse, QaResponse, SatisfyResponse,
  ValidateResponse, SaveResponse, RequirementsResponse, Violation, Concept, Relation, ProjectResponse,
} from "../types/contracts";
import {
  ApiCallError, type PkmsApi, type StreamHandlers, type StreamRequest,
  type StreamController, type ValidateRequest, type SaveRequest,
  type SatisfyRequest, type QaRequest, type RequirementsRequest, type CreateProjectRequest,
  type ABExtractRequest, type ABExtractResponse,
} from "./types";

import health from "../mocks/fixtures/health.json";
import streamS1 from "../mocks/fixtures/extraction_stream_S1.json";
import validateRange from "../mocks/fixtures/extraction_validate_range_violation.json";
import saveS1 from "../mocks/fixtures/extraction_save_S1.json";
import satisfyBad from "../mocks/fixtures/satisfy_bad.json";
import satisfyGood from "../mocks/fixtures/satisfy_good.json";
import satisfyPending from "../mocks/fixtures/satisfy_pending_missing.json";
import satisfyScopeB from "../mocks/fixtures/satisfy_scope_B.json";
import qaCompare from "../mocks/fixtures/qa_compare_suv600.json";
import qaInsufficient from "../mocks/fixtures/qa_insufficient.json";
import qaLayerA from "../mocks/fixtures/qa_layerA_599.json";
import graphTip from "../mocks/fixtures/graph_tipchatter.json";
import reqParse from "../mocks/fixtures/project_requirements_parse.json";
import errTimeout from "../mocks/fixtures/error_llm_timeout.json";

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

// fixture 의 _comment/_request 등 문서용 키는 제거하고 계약 형태로만 노출
const strip = <T>(o: unknown): T => {
  const clone = JSON.parse(JSON.stringify(o));
  for (const k of Object.keys(clone)) if (k.startsWith("_")) delete clone[k];
  return clone as T;
};

/** extraction/stream mock — 시나리오를 입력 텍스트로 라우팅. */
function extractionStream(req: StreamRequest, h: StreamHandlers): StreamController {
  let cancelled = false;
  const ctrl: StreamController = { cancel: () => { cancelled = true; } };
  const text = req.text ?? "";

  (async () => {
    // 에러 시나리오: 계약 §5 — 그때까지 렌더 유지 + "다시 시도" (자동 재연결 금지)
    const errorScenario = text.includes("!error") || text.includes("타임아웃");
    // 위반 시나리오: 'causes 치역' range 위반 → severity:violation → CD-7 저장 차단
    const violationScenario = text.includes("경도");

    await delay(250); if (cancelled) return;
    h.onStatus?.({ stage: "extract", msg: "개념 추출 중" });

    if (violationScenario) {
      await delay(350); if (cancelled) return;
      h.onConcept?.({ label: "경도", type: "Attribute", span: [0, 2] });
      await delay(300); if (cancelled) return;
      h.onConcept?.({ label: "겨울철", type: "EnvCondition", iri: "http://ex.org/domain#Winter", span: [6, 9] });
      await delay(300); if (cancelled) return;
      h.onRelation?.({ subject: "경도", predicate: "causes", object: "겨울철", evidence: text, confidence: 0.71 });
      if (errorScenario) { await delay(300); if (cancelled) return; h.onError?.(strip(errTimeout)); return; }
      await delay(350); if (cancelled) return;
      h.onStatus?.({ stage: "validate", msg: "명세 검증 중" });
      await delay(500); if (cancelled) return;
      const v = strip<ValidateResponse>(validateRange);
      h.onValidation?.({ conforms: v.conforms, violations: v.violations });
      await delay(250); if (cancelled) return;
      h.onDone?.({ thread_id: "thread-mock-err", draft_id: "draft-mock-err", trace_id: v.trace_id });
      return;
    }

    // 정상 시나리오 — extraction_stream_S1.json 이벤트 순서 그대로
    const events = (streamS1 as { events: { event: string; data: unknown }[] }).events;
    for (const ev of events) {
      await delay(ev.event === "concept" || ev.event === "relation" ? 350 : 300);
      if (cancelled) return;
      switch (ev.event) {
        case "status": h.onStatus?.(ev.data as never); break;
        case "concept": h.onConcept?.(ev.data as Concept); break;
        case "relation": h.onRelation?.(ev.data as Relation); break;
        case "validation": h.onValidation?.(ev.data as never); break;
        case "done": h.onDone?.(ev.data as never); break;
      }
      if (errorScenario && ev.event === "relation") { await delay(300); if (cancelled) return; h.onError?.(strip(errTimeout)); return; }
    }
  })();

  return ctrl;
}

async function satisfy(req: SatisfyRequest): Promise<SatisfyResponse> {
  await delay(600);
  const d = req.design;
  // 판정 보류: 필수 수치 결측 (CD-8) — spring_n 누락
  if (d.spring_n === undefined || d.spring_n === null) return strip<SatisfyResponse>(satisfyPending);
  // 지식범위 [떨림] 만 — scope-B
  if (req.categories && req.categories.length === 1 && req.categories[0] === "떨림") return strip<SatisfyResponse>(satisfyScopeB);
  // 만족: 실리콘 설계
  if (d.material === "Silicone") return strip<SatisfyResponse>(satisfyGood);
  // 불만족: 고무 설계 (기본)
  return strip<SatisfyResponse>(satisfyBad);
}

async function qa(req: QaRequest): Promise<QaResponse> {
  await delay(700);
  const q = req.question ?? "";
  const domainOutside = /타이어|공기압|psi/.test(q);
  if (domainOutside) return strip<QaResponse>(qaInsufficient);
  // A계층: 규칙·수치 질문 (verified 모드 또는 '안전 길이' 질의)
  if (req.mode === "verified" && /안전\s*길이|몇\s*mm|안전길이/.test(q)) return strip<QaResponse>(qaLayerA);
  if (req.mode === "verified") {
    const a = strip<QaResponse>(qaCompare);
    return { ...a, llm_answer: null, comparison: null };
  }
  // 기본 compare: B계층 satisfy 대조
  return strip<QaResponse>(qaCompare);
}

async function graph(_params: Record<string, string>): Promise<GraphResponse> {
  await delay(300);
  return strip<GraphResponse>(graphTip);
}

async function extractionValidate(req: ValidateRequest): Promise<ValidateResponse> {
  await delay(300);
  // 'causes' 대상이 Symptom 이 아니면 range 위반 — fixture 그대로
  const bad = req.relations.some((r) => r.predicate === "causes" &&
    req.concepts.find((c) => c.label === r.object)?.type !== "Symptom");
  if (bad) return strip<ValidateResponse>(validateRange);
  return { conforms: true, violations: [] as Violation[], trace_id: "trace-validate-mock" };
}

async function extractionSave(req: SaveRequest): Promise<SaveResponse> {
  await delay(500);
  // HITL 게이트: 미승인이면 409 GUARDRAIL_BLOCKED
  if (req.approved !== true) {
    throw new ApiCallError({
      code: "GUARDRAIL_BLOCKED",
      user_message: "명세 위반이 남아 있어 저장할 수 없습니다. 경고를 해소한 뒤 승인해 주세요.",
      trace_id: "trace-save-blocked",
    });
  }
  return strip<SaveResponse>(saveS1);
}

async function parseRequirements(_projectId: string, req: RequirementsRequest): Promise<RequirementsResponse> {
  await delay(500);
  const base = strip<RequirementsResponse & { _variant_unknown_symptom?: unknown }>(reqParse);
  // 미지 증상 변형: '유막' 등 M1 에 없는 증상 → unknown_symptoms
  if (/유막|시야/.test(req.text)) {
    const variant = (reqParse as { _variant_unknown_symptom: { requirements: RequirementsResponse["requirements"]; unknown_symptoms: string[]; trace_id: string } })._variant_unknown_symptom;
    return { requirements: variant.requirements, unknown_symptoms: variant.unknown_symptoms, trace_id: variant.trace_id };
  }
  return { requirements: base.requirements, unknown_symptoms: base.unknown_symptoms, trace_id: base.trace_id };
}

async function createProject(req: CreateProjectRequest): Promise<ProjectResponse> {
  await delay(300);
  const id = `mock-${Date.now().toString(36)}`;
  return {
    id, iri: `http://ex.org/eng#Proj_${id}`, name: req.name,
    target_vehicle: req.target_vehicle, target_env: req.target_env,
    knowledge_categories: req.knowledge_categories ?? [],
    requirements: [], designs: [], trace_id: "trace-proj-mock",
  };
}

// T-90 A/B — mock 은 관찰된 패턴(solar=복합어 원자 / claude=분해)을 데모로 보여준다(실제 판정 아님).
async function extractionAB(req: ABExtractRequest): Promise<ABExtractResponse> {
  await delay(300);
  const providers = req.providers ?? ["solar", "claude"];
  const decompose = /블레이드/.test(req.text);
  const results = providers.map((p) => {
    if (p === "claude" && decompose) {
      return { requested_provider: p, actual_provider: p,
        concepts: [{ label: "고무", type: "Material" }, { label: "블레이드", type: "Component" }] as Concept[],
        relations: [{ subject: "블레이드", predicate: "hasMaterial", object: "고무" }] as Relation[] };
    }
    return { requested_provider: p, actual_provider: p,
      concepts: [{ label: req.text.trim(), type: "PartType" }] as Concept[], relations: [] as Relation[] };
  });
  return { text: req.text, results, trace_id: "mock" };
}

export const mockApi: PkmsApi = {
  health: async () => { await delay(150); return strip<HealthResponse>(health); },
  extractionStream,
  extractionAB,
  extractionValidate,
  extractionSave,
  satisfy,
  qa,
  graph,
  createProject,
  parseRequirements,
};
