import { beforeEach, describe, expect, it } from "vitest";

import type { AIGateway } from "../src/services/ai/gateway.js";
import type { ExtractionEvent } from "../src/services/ai/types.js";
import { createKnowledgeMock } from "../src/services/knowledgeMock.js";
import type { Deps } from "../src/routes/deps.js";
import { _resetSavedDrafts } from "../src/routes/extraction.js";
import { appFor, postJson, readSse, withServer } from "./util.js";

beforeEach(() => _resetSavedDrafts());

describe("T-51 /extraction/stream (SSE)", () => {
  it("이벤트 순서 계약: status* → concept*|relation* → validation → done", async () => {
    await withServer(appFor(), async (base) => {
      const events = await readSse(base, "/api/v1/extraction/stream", {
        text: "겨울철 저온에서 고무 블레이드는 소음이 발생한다",
      });
      const kinds = events.map((e) => e.event);
      expect(kinds[0]).toBe("status");
      expect(kinds.at(-1)).toBe("done");
      expect(kinds).toContain("concept");
      expect(kinds).toContain("validation");
      // validation 은 done 직전, concept/relation 뒤.
      const iValidation = kinds.indexOf("validation");
      const iDone = kinds.indexOf("done");
      const iLastConcept = kinds.lastIndexOf("concept");
      expect(iLastConcept).toBeLessThan(iValidation);
      expect(iValidation).toBeLessThan(iDone);
      // done 에 trace_id·draft_id·thread_id.
      const done = events.find((e) => e.event === "done")!;
      expect(done.data.trace_id).toBeTruthy();
      expect(done.data.draft_id).toBeTruthy();
      expect(done.data.thread_id).toBeTruthy();
      // validation 은 지식서비스 결과 (정상 → conforms true).
      const v = events.find((e) => e.event === "validation")!;
      expect(v.data.conforms).toBe(true);
    });
  });

  it("음성: 중간 error 발생 시 부분 결과 유지 + error 이벤트로 종료", async () => {
    // extract 가 개념 하나를 흘린 뒤 던지는 gateway 를 주입한다.
    const failingGateway = {
      async *extract(): AsyncIterable<ExtractionEvent> {
        yield { kind: "status", stage: "extract", msg: "개념 추출 중" };
        yield { kind: "concept", concept: { label: "겨울철", type: "EnvCondition" } };
        throw new Error("LLM stream boom");
      },
    } as unknown as AIGateway;

    const deps: Deps = {
      makeGateway: () => failingGateway,
      makeKnowledge: (t) => createKnowledgeMock(t),
    };

    await withServer(appFor(deps), async (base) => {
      const events = await readSse(base, "/api/v1/extraction/stream", { text: "겨울철 고무 소음" });
      const kinds = events.map((e) => e.event);
      // 부분 결과(concept) 유지.
      expect(kinds).toContain("concept");
      // validation·done 없이 error 로 종료.
      expect(kinds).not.toContain("done");
      expect(kinds.at(-1)).toBe("error");
      const err = events.at(-1)!;
      expect(err.data.trace_id).toBeTruthy();
      expect(err.data.code).toBeTruthy();
    });
  });
});

describe("T-51 /extraction/validate", () => {
  it("range 위반 입력 → conforms false + severity violation (fixture 일치)", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await postJson(base, "/api/v1/extraction/validate", {
        concepts: [
          { label: "경도", type: "Attribute" },
          { label: "겨울철", type: "EnvCondition", iri: "http://ex.org/domain#Winter" },
        ],
        relations: [{ subject: "경도", predicate: "causes", object: "겨울철" }],
      });
      expect(status).toBe(200);
      expect(body.conforms).toBe(false);
      const violations = body.violations as Array<{ code: string; severity: string }>;
      expect(violations[0]?.code).toBe("causes_range");
      expect(violations[0]?.severity).toBe("violation");
    });
  });
});

describe("T-51 /extraction/save — HITL 게이트", () => {
  const goodBody = {
    sentence_text: "겨울철 저온에서 고무는 경도가 상승해 소음을 유발한다.",
    concepts: [
      { label: "겨울철", type: "EnvCondition" },
      { label: "고무", type: "Material" },
      { label: "소음", type: "Symptom" },
    ],
    relations: [{ subject: "고무", predicate: "causes", object: "소음", evidence: "S1" }],
    category: "소음",
    approved: true,
    draft_id: "draft-happy-1",
  };

  it("정상 저장 → 201 + 멱등(같은 draft_id 재요청 동일 응답)", async () => {
    await withServer(appFor(), async (base) => {
      const first = await postJson(base, "/api/v1/extraction/save", goodBody);
      expect(first.status).toBe(201);
      expect((first.body.sentence as Record<string, unknown>).id).toBe("S1");
      const second = await postJson(base, "/api/v1/extraction/save", { ...goodBody });
      expect(second.status).toBe(201);
      expect(second.body.sentence).toEqual(first.body.sentence);
    });
  });

  it("음성: approved:false → 409 GUARDRAIL_BLOCKED", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await postJson(base, "/api/v1/extraction/save", {
        ...goodBody,
        draft_id: "draft-noapprove",
        approved: false,
      });
      expect(status).toBe(409);
      expect(body.code).toBe("GUARDRAIL_BLOCKED");
    });
  });

  it("음성: 위조된 violations:[] + 실제 위반 입력 → 서버 재검증으로 409", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await postJson(base, "/api/v1/extraction/save", {
        sentence_text: "경도가 겨울철을 유발한다.",
        concepts: [
          { label: "경도", type: "Attribute" },
          { label: "겨울철", type: "EnvCondition" },
        ],
        relations: [{ subject: "경도", predicate: "causes", object: "겨울철" }],
        category: "소음",
        approved: true,
        draft_id: "draft-forged",
        // 클라이언트가 위반이 없다고 위조 — BFF 는 재검증한다.
        violations: [],
      });
      expect(status).toBe(409);
      expect(body.code).toBe("GUARDRAIL_BLOCKED");
    });
  });

  it("422: 잘못된 concept type → VALIDATION_ERROR", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await postJson(base, "/api/v1/extraction/validate", {
        concepts: [{ label: "x", type: "NotAType" }],
        relations: [],
      });
      expect(status).toBe(422);
      expect(body.code).toBe("VALIDATION_ERROR");
    });
  });
});
