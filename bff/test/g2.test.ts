/** G2 통합에서 발견된 결함 D1~D4 회귀 테스트. */
import { describe, expect, it } from "vitest";

import { defaultDeps } from "../src/routes/deps.js";
import type { Deps } from "../src/routes/deps.js";
import { AIGateway } from "../src/services/ai/gateway.js";
import { MockProvider } from "../src/services/ai/mockProvider.js";
import { EmptyContextError } from "../src/services/ai/types.js";
import { createKnowledgeMock } from "../src/services/knowledgeMock.js";
import type { KnowledgeClient } from "../src/services/knowledgeClient.js";
import { appFor, postJson, withServer } from "./util.js";

const designBad = {
  id: "Blade_bad",
  material: "Rubber",
  length_mm: 600,
  spring_n: 8,
  arm_shape: "simple",
  vehicle: "MidSizeSUV",
  env: "Winter",
};

describe("D1 — /satisfy 가 프로젝트 지식범위(CD-4)를 적용한다", () => {
  it("동일 설계, 다른 프로젝트: A(소음+떨림)=4위반 · B(떨림만)=3위반", async () => {
    await withServer(appFor(), async (base) => {
      const a = await postJson(base, "/api/v1/satisfy", { project_id: "proj-winter-suv", design: designBad });
      const b = await postJson(base, "/api/v1/satisfy", { project_id: "proj-vibration-lab", design: designBad });
      expect(a.body.violations).toEqual(["S1", "S3", "S4", "S6"]);
      expect(a.body.applied_categories).toEqual(["소음", "떨림"]);
      // B 는 소음 규칙(S1) 제외 — 지식범위가 실제로 적용됐음을 증명.
      expect(b.body.violations).toEqual(["S3", "S4", "S6"]);
      expect(b.body.applied_categories).toEqual(["떨림"]);
    });
  });
});

describe("D2 — BFF 는 satisfy.require 를 null 이 아니라 [] 로 보낸다", () => {
  // 내부 SatisfyRequest.require 는 null 을 422 로 거부한다. 그 계약을 흉내낸 stub 로 검증.
  function strictRequireDeps(): Deps {
    return {
      makeGateway: defaultDeps.makeGateway,
      makeKnowledge: (t): KnowledgeClient => {
        const base = createKnowledgeMock(t);
        return {
          ...base,
          satisfy: async (req) => {
            const r = req as { require?: unknown };
            if (r.require === null || r.require === undefined || !Array.isArray(r.require)) {
              throw new Error("SIM 422: require must be a list");
            }
            return base.satisfy(req);
          },
        };
      },
    };
  }

  it("/satisfy 는 require 없이도 200 (null 로 죽지 않는다)", async () => {
    await withServer(appFor(strictRequireDeps()), async (base) => {
      const { status } = await postJson(base, "/api/v1/satisfy", { project_id: "proj-winter-suv", design: designBad });
      expect(status).toBe(200);
    });
  });

  it("/qa B계층(compare) 이 satisfy 422 없이 200", async () => {
    await withServer(appFor(strictRequireDeps()), async (base) => {
      const { status, body } = await postJson(base, "/api/v1/qa", {
        question: "중형 SUV에 고무 600mm 써도 될까?",
        mode: "compare",
      });
      expect(status).toBe(200);
      expect(body.layer).toBe("B");
    });
  });
});

describe("D3 — A계층 답변에 결정론 수치가 담긴다", () => {
  it('"안전 길이" 질문 → verified_answer.text 에 599 포함', async () => {
    await withServer(appFor(), async (base) => {
      const { body } = await postJson(base, "/api/v1/qa", { question: "중형 SUV 안전 길이는?", mode: "verified" });
      const text = (body.verified_answer as { text: string }).text;
      expect(text).toContain("599");
    });
  });
});

describe("D4/CD-12 — insufficient_evidence 가 실제로 발화한다", () => {
  it("도메인 밖 질문 → 도메인 접지 실패 → insufficient_evidence true, sources 0", async () => {
    await withServer(appFor(), async (base) => {
      const { body } = await postJson(base, "/api/v1/qa", {
        question: "타이어 공기압은 얼마로 맞춰야 하나요?",
        mode: "verified",
      });
      expect(body.layer).toBe("C");
      expect(body.insufficient_evidence).toBe(true);
      expect((body.verified_answer as { sources: unknown[] }).sources).toEqual([]);
      expect((body.verified_answer as { text: string }).text).toContain("명세 근거 없음");
    });
  });

  it("도메인 안 질문(검증 근거 있음) → insufficient_evidence false", async () => {
    await withServer(appFor(), async (base) => {
      const { body } = await postJson(base, "/api/v1/qa", {
        question: "겨울에 고무 블레이드를 쓰면 소음이 나나요?",
        mode: "verified",
      });
      expect(body.layer).toBe("C");
      expect(body.insufficient_evidence).toBe(false);
      expect(((body.verified_answer as { sources: unknown[] }).sources).length).toBeGreaterThan(0);
    });
  });
});

describe("D6 — /extraction/save 성공 경로 + kgSave 가 approved 를 forward", () => {
  it("위반 없는 문장 + approved:true → 201 + sentence·derived·human_view", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await postJson(base, "/api/v1/extraction/save", {
        sentence_text: "실리콘 블레이드는 저온에서 소음을 해소한다.",
        category: "소음",
        approved: true,
        draft_id: "d6-happy-1",
        concepts: [
          { label: "실리콘", type: "Material" },
          { label: "소음", type: "Symptom" },
        ],
        relations: [{ subject: "실리콘", predicate: "mitigates", object: "소음" }],
      });
      expect(status).toBe(201);
      expect(body.sentence).toBeTruthy();
      const derived = body.derived as { rule?: unknown; shapes?: unknown };
      expect(derived.rule).toBeTruthy();
      expect(Array.isArray(derived.shapes)).toBe(true);
      expect(Array.isArray(body.human_view)).toBe(true);
    });
  });

  it("mock 은 계약만큼 엄격: kgSave 는 approved 누락 시 실제 서비스처럼 422 (D6 재발 방지)", async () => {
    const kn = createKnowledgeMock("t");
    await expect(
      kn.kgSave({ sentence_text: "x", category: "소음", concepts: [], relations: [] }),
    ).rejects.toMatchObject({ code: "VALIDATION_ERROR", httpStatus: 422 });
    // satisfy 도 require=null 을 거부(D2 병과 동종)
    await expect(
      kn.satisfy({ design: { material: "Rubber", vehicle: "MidSizeSUV" }, require: null }),
    ).rejects.toMatchObject({ code: "VALIDATION_ERROR" });
  });
});

describe("CD-13 — 가드레일은 라우팅보다 앞 · 전 계층 fail-closed · 입력 날조 금지", () => {
  // 계층을 강제 주입해 각 계층의 fail-closed 를 직접 단언한다(코디 지시).
  function forcedGateway(layer: "A" | "B" | "C", conceptLabels: Array<[string, string]>): AIGateway {
    return {
      // eslint-disable-next-line require-yield
      async *extract() {
        for (const [label, type] of conceptLabels) yield { kind: "concept", concept: { label, type } };
      },
      async classify() {
        return layer;
      },
      async answer() {
        return "무근거 LLM 답변";
      },
      providerName() {
        return "mock";
      },
    } as unknown as AIGateway;
  }

  function depsWith(gw: AIGateway, knOverride?: Partial<KnowledgeClient>): Deps {
    return {
      makeGateway: () => gw,
      makeKnowledge: (t) => ({ ...createKnowledgeMock(t), ...knOverride }) as KnowledgeClient,
    };
  }

  it("A fail-closed: 화이트리스트 미매칭(A 강제) → insufficient, sources[] (폴백 금지)", async () => {
    const deps = depsWith(forcedGateway("A", [["중형 SUV", "VehicleType"]]));
    await withServer(appFor(deps), async (base) => {
      const { body } = await postJson(base, "/api/v1/qa", { question: "엔진 오일 교환 주기는?", mode: "verified" });
      expect(body.layer).toBe("A");
      expect(body.insufficient_evidence).toBe(true);
      expect((body.verified_answer as { sources: unknown[] }).sources).toEqual([]);
    });
  });

  it("B fail-closed: material·vehicle 못 얻음(B 강제) → 판정 보류(insufficient, sources[]) — 확정 판정 금지", async () => {
    const deps = depsWith(forcedGateway("B", [["알루미늄", "Material"]]));
    await withServer(appFor(deps), async (base) => {
      const { body } = await postJson(base, "/api/v1/qa", {
        question: "노트북에 알루미늄 700mm 써도 될까?",
        mode: "verified",
      });
      expect(body.layer).toBe("B");
      expect(body.insufficient_evidence).toBe(true);
      expect((body.verified_answer as { sources: unknown[] }).sources).toEqual([]);
      expect((body.verified_answer as { text: string }).text).toContain("판정 보류");
    });
  });

  it("C fail-closed: 미지 개념 1건이라도(C 강제) → insufficient, sources[]", async () => {
    const gw = forcedGateway("C", [
      ["고무", "Material"],
      ["자전거 체인", "Component"],
    ]);
    // 지식서비스가 '자전거 체인' 을 unknown_concept 로 판정했다고 가정.
    const deps = depsWith(gw, {
      async validateShacl() {
        return {
          conforms: false,
          violations: [{ code: "unknown_concept", severity: "warning", offender: "자전거 체인", message: "미지 개념" }],
          trace_id: "t",
        };
      },
    });
    await withServer(appFor(deps), async (base) => {
      const { body } = await postJson(base, "/api/v1/qa", {
        question: "자전거 체인에 고무 윤활유 써도 될까?",
        mode: "verified",
      });
      expect(body.layer).toBe("C");
      expect(body.insufficient_evidence).toBe(true);
      expect((body.verified_answer as { sources: unknown[] }).sources).toEqual([]);
    });
  });

  it("접지: 인식 개념 0 → 계층 무관 insufficient (B 로 분류돼도)", async () => {
    const deps = depsWith(forcedGateway("B", [])); // 추출 개념 0
    await withServer(appFor(deps), async (base) => {
      const { body } = await postJson(base, "/api/v1/qa", { question: "타이어 공기압은 얼마인가?", mode: "verified" });
      expect(body.insufficient_evidence).toBe(true);
      expect((body.verified_answer as { sources: unknown[] }).sources).toEqual([]);
    });
  });

  it("no-op 아님(정상 질문은 여전히 통과): A 599 · C 근거 · B 확정 판정", async () => {
    await withServer(appFor(), async (base) => {
      const a = await postJson(base, "/api/v1/qa", { question: "중형 SUV 안전 길이는?", mode: "verified" });
      expect(a.body.layer).toBe("A");
      expect(a.body.insufficient_evidence).toBe(false);
      expect((a.body.verified_answer as { text: string }).text).toContain("599");

      const c = await postJson(base, "/api/v1/qa", { question: "겨울에 고무 블레이드 쓰면 소음이 나나요?", mode: "verified" });
      expect(c.body.layer).toBe("C");
      expect(c.body.insufficient_evidence).toBe(false);
      expect(((c.body.verified_answer as { sources: unknown[] }).sources).length).toBeGreaterThan(0);

      const b = await postJson(base, "/api/v1/qa", {
        question: "중형 SUV에 고무 600mm 스프링 8N simple 암 써도 될까?",
        mode: "verified",
      });
      expect(b.body.layer).toBe("B");
      expect(b.body.insufficient_evidence).toBe(false);
      expect((b.body.verified_answer as { determinism: string }).determinism).toBe("satisfy");
    });
  });
});

describe("CD-14 — 근거 없는 answer() 는 곧 환각. 검증답변과 llm_answer 를 타입으로 분리", () => {
  it("answer(q, []) → throw (provider·gateway 둘 다)", async () => {
    const p = new MockProvider();
    await expect(p.answer("q", [])).rejects.toBeInstanceOf(EmptyContextError);
    const gw = new AIGateway("t", { primary: new MockProvider() });
    await expect(gw.answer("q", [])).rejects.toBeInstanceOf(EmptyContextError);
    // llmOnlyAnswer 는 근거 없이도 동작(환각비교 전용).
    await expect(gw.llmOnlyAnswer("q")).resolves.toContain("무근거");
  });

  it("수치 부족 B(판정 보류) → insufficient·sources[]·판정보류 텍스트 + answer() 미호출", async () => {
    const calls = { answer: 0, llmOnly: 0 };
    const spyGw = {
      // eslint-disable-next-line require-yield
      async *extract() {
        yield { kind: "concept", concept: { label: "고무", type: "Material" } };
        yield { kind: "concept", concept: { label: "중형 SUV", type: "VehicleType" } };
      },
      async classify() {
        return "B";
      },
      async answer() {
        calls.answer++;
        return "이 문자열이 나오면 안 된다";
      },
      async llmOnlyAnswer() {
        calls.llmOnly++;
        return "llm-only";
      },
      providerName() {
        return "mock";
      },
    } as unknown as AIGateway;
    const deps: Deps = { makeGateway: () => spyGw, makeKnowledge: (t) => createKnowledgeMock(t) };

    await withServer(appFor(deps), async (base) => {
      const { body } = await postJson(base, "/api/v1/qa", {
        question: "중형 SUV에 고무 600mm 써도 될까?", // 스프링·암형상 미지정 → satisfy 판정 보류
        mode: "verified",
      });
      expect(body.layer).toBe("B");
      expect(body.insufficient_evidence).toBe(true);
      expect((body.verified_answer as { sources: unknown[] }).sources).toEqual([]);
      expect((body.verified_answer as { text: string }).text).toContain("판정 보류");
      // CD-14 핵심: 막다른 길에서 LLM 으로 흘러내리지 않았다.
      expect(calls.answer).toBe(0);
    });
  });

  it("compare 모드는 분리 후에도 살아 있다: 판정 보류여도 llm_answer 생성", async () => {
    await withServer(appFor(), async (base) => {
      const { body } = await postJson(base, "/api/v1/qa", {
        question: "중형 SUV에 고무 600mm 써도 될까?",
        mode: "compare",
      });
      expect(body.insufficient_evidence).toBe(true); // 판정 보류
      const llm = body.llm_answer as { text: string; model: string } | null;
      expect(llm).not.toBeNull(); // 환각비교는 계속 동작
      expect(llm?.model).toBe("mock");
    });
  });
});
