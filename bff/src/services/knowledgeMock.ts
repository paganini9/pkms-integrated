/**
 * 지식서비스 mock — contracts/mocks 를 반환하는 선행 구현 (병렬 규약).
 * 요청을 보고 알맞은 fixture 를 고른다. 판정 로직은 여기 없다 —
 * fixture 가 이미 지식서비스의 결정론 판정 결과다(BFF 는 통과만).
 */
import { BuiltinLocked, ValidationError } from "../core/errors.js";
import { loadFixture, readFixtureRaw, stripMeta } from "./fixtures.js";
import type {
  GraphQuery, KnowledgeClient, LookupRes, NamedQuery, RagRes, ValidateRes, Violation,
} from "./knowledgeClient.js";

const BUILTIN_CONCEPTS = new Set([
  "Symptom", "Behavior", "Material", "EnvCondition", "VehicleType", "PartType", "Component", "Attribute",
]);

const ENV_LABELS = new Set(["겨울철", "겨울", "저온"]);

interface ReqConcepts {
  concepts?: Array<{ label: string; type?: string }>;
  relations?: Array<{ subject: string; predicate: string; object: string }>;
}

/** causes 의 대상이 EnvCondition 이면 range 위반 (extraction_validate_range_violation). */
function detectRangeViolation(req: ReqConcepts): boolean {
  const concepts = req.concepts ?? [];
  for (const rel of req.relations ?? []) {
    if (rel.predicate !== "causes") continue;
    const obj = concepts.find((c) => c.label === rel.object);
    if ((obj && obj.type === "EnvCondition") || ENV_LABELS.has(rel.object)) return true;
  }
  return false;
}

interface SatisfyReq {
  design?: { material?: string; vehicle?: string; spring_n?: number | null; length_mm?: number | null };
  require?: string[];
  categories?: string[] | null;
}

function pickSatisfyFixture(req: SatisfyReq): string {
  const d = req.design ?? {};
  if (d.spring_n === null || d.spring_n === undefined) return "satisfy_pending_missing";
  const cats = req.categories ?? undefined;
  if (cats && cats.length === 1 && cats[0] === "떨림") return "satisfy_scope_B";
  if (d.material === "Silicone") return "satisfy_good";
  return "satisfy_bad";
}

const MAX_SAFE: Record<string, { mm: number; sentence: string }> = {
  MidSizeSUV: { mm: 599, sentence: "S3" },
  CompactSedan: { mm: 550, sentence: "S5" },
};

const S_TEXT: Record<string, { iri: string; text: string }> = {
  S3: { iri: "http://ex.org/domain#S3", text: "중형 SUV에서 블레이드 길이가 600mm 이상이면 끝단 떨림이 발생할 수 있다." },
  S5: { iri: "http://ex.org/domain#S5", text: "소형 세단은 550mm까지는 끝단 떨림 문제가 없다." },
};

export function createKnowledgeMock(traceId: string): KnowledgeClient {
  const withTrace = <T>(o: T): T & { trace_id: string } => ({ ...o, trace_id: traceId });

  return {
    async health() {
      return { status: "ok", store: "ok", reasoner: "no_jre", rag: "ok" };
    },

    async validateShacl(req): Promise<ValidateRes> {
      if (detectRangeViolation(req as ReqConcepts)) {
        const fx = loadFixture("extraction_validate_range_violation");
        return withTrace({ conforms: false, violations: fx.violations as Violation[] });
      }
      return withTrace({ conforms: true, violations: [] as Violation[] });
    },

    async satisfy(req) {
      // 계약 하한이 아니라 계약 그 자체 — 실제 SatisfyRequest.require 는 null 을 거부(422)한다.
      const r = req as SatisfyReq & { require?: unknown };
      if (r.require === null) {
        throw new ValidationError("mock satisfy: require=null (내부 계약은 list 를 요구)", { field: "require" });
      }
      const d = r.design ?? {};
      if (!d.material || !d.vehicle) {
        throw new ValidationError("mock satisfy: design.material·vehicle 필수", { field: "design" });
      }
      const fx = loadFixture(pickSatisfyFixture(r));
      return withTrace(fx);
    },

    async kgSave(req) {
      // 실제 SaveRequest 와 동일한 하드 게이트를 mock 에도 건다(D6 재발 방지).
      const r = (req ?? {}) as {
        approved?: unknown;
        sentence_text?: unknown;
        category?: unknown;
        concepts?: unknown;
        relations?: unknown;
      };
      const missing: string[] = [];
      if (r.approved !== true) missing.push("approved"); // Literal[True] — 누락·false 모두 422
      if (typeof r.sentence_text !== "string" || r.sentence_text.length === 0) missing.push("sentence_text");
      if (typeof r.category !== "string" || r.category.length === 0) missing.push("category");
      if (!Array.isArray(r.concepts)) missing.push("concepts");
      if (!Array.isArray(r.relations)) missing.push("relations");
      if (missing.length > 0) {
        throw new ValidationError(`mock kgSave: 필수 필드 누락/오류 ${missing.join(",")}`, { fields: missing });
      }
      return withTrace(loadFixture("extraction_save_S1"));
    },

    async kgLookup(query: NamedQuery, params: Record<string, string>): Promise<LookupRes> {
      if (query === "max_safe_length") {
        const vehicle = params.vehicle ?? "MidSizeSUV";
        const hit = MAX_SAFE[vehicle];
        if (!hit) return withTrace({ query, rows: [], sources: [] });
        const st = S_TEXT[hit.sentence];
        return withTrace({
          query,
          rows: [{ vehicle, max_safe_mm: hit.mm, sentence: hit.sentence }],
          sources: st ? [{ sentence: hit.sentence, iri: st.iri, text: st.text }] : [],
        });
      }
      // 그 밖의 명명 질의는 빈 결과(억지 답 금지 경로로 간다).
      return withTrace({ query, rows: [], sources: [] });
    },

    async ragSearch(req): Promise<RagRes> {
      const r = req as { query?: string; project_id?: string };
      const q = r.query ?? "";
      const domain = /고무|겨울|블레이드|소음|실리콘|떨림|와이퍼|암/.test(q);
      if (!domain) return withTrace({ hits: [], sufficient: false });
      const raw = readFixtureRaw("rag_search_winter_rubber");
      const src =
        r.project_id && /vibration/.test(r.project_id)
          ? stripMeta(raw._variant_out_of_scope as Record<string, unknown>)
          : stripMeta(raw);
      return withTrace({ hits: src.hits as RagRes["hits"], sufficient: src.sufficient as boolean });
    },

    async rulesCompile(categories) {
      return withTrace({ rules: [], shapes: [], human_view: [], compiled_gates: (categories ?? ["소음", "떨림"]).length + 1 });
    },
    async rulesDryRun() {
      return withTrace({ new_violations: [], affected_instances: [] });
    },
    async reasonConsistency() {
      return withTrace({ consistent: true, clashes: [], dl_axioms: [] });
    },

    async graph(_q: GraphQuery) {
      return withTrace(loadFixture("graph_tipchatter"));
    },

    async dashboard() {
      return withTrace({
        m0: { classes: 18, relations: 9 },
        m1: { sentences: 6, rules: 5, concepts: 12 },
        m2: { projects: 1, designs: 2, violations: 4 },
        recent: [{ kind: "sentence", id: "S6", label: "와이퍼 암 형상이 단순하면...", at: "2026-07-10T00:00:00Z" }],
      });
    },

    async governanceConcepts() {
      return withTrace({
        builtin: [...BUILTIN_CONCEPTS].map((id) => ({ id, label: id })),
        custom: [],
      });
    },
    async governanceCreate(req) {
      const r = (req ?? {}) as Record<string, unknown>;
      return withTrace({ id: r.id ?? "Custom", label: r.label ?? "", parent: r.parent ?? "Symptom" });
    },
    async governanceDelete(id) {
      if (BUILTIN_CONCEPTS.has(id)) throw new BuiltinLocked(`builtin delete: ${id}`);
      return withTrace({ deleted: true, id });
    },

    async upperOntologyClasses() {
      return withTrace({
        classes: [{ id: "Symptom", parent: "owl:Thing", children: ["Noise", "TipChatter"] }],
        relations: [{ id: "causes", domain: "Thing", range: "Symptom" }],
      });
    },
    async upperOntologyCreate(req) {
      return withTrace({ applied: true, changes: (req as Record<string, unknown>)?.changes ?? [] });
    },
    async upperOntologyImpact() {
      return withTrace({ affected_m1: ["S1"], affected_m2: ["Blade_bad"] });
    },

    async rules() {
      return withTrace({ rules: [], shapes: [], human_view: [] });
    },
    async ruleImpact() {
      return withTrace({ affected_instances: [] });
    },

    async createProject(req) {
      const r = (req ?? {}) as Record<string, unknown>;
      return withTrace({
        id: "proj-mock-0001",
        iri: "http://ex.org/eng#Proj_Mock",
        name: r.name ?? "프로젝트",
        target_vehicle: r.target_vehicle ?? null,
        target_env: r.target_env ?? null,
        knowledge_categories: r.knowledge_categories ?? [],
        requirements: [],
        designs: [],
      });
    },
    async getProject(id) {
      // 프로젝트별 지식범위(CD-4) — D1 회귀: vibration-lab 은 [떨림] 만.
      const vibration = /vibration/.test(id);
      return withTrace({
        id,
        name: vibration ? "떨림 실험실" : "겨울용 SUV 와이퍼",
        target_vehicle: "MidSizeSUV",
        target_env: "Winter",
        knowledge_categories: vibration ? ["떨림"] : ["소음", "떨림"],
        requirements: [],
        designs: [],
      });
    },
    async setKnowledgeScope(_id, req) {
      const cats = ((req as Record<string, unknown>)?.categories as string[]) ?? [];
      return withTrace({ categories: cats, compiled_gates: cats.length + 1 });
    },
    async categories() {
      return withTrace({
        categories: [
          { name: "소음", sentences: 2, rules: 2 },
          { name: "떨림", sentences: 4, rules: 3 },
        ],
      });
    },
  };
}
