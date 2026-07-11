/** g3.1 — 태스크별 기본 provider 정책. 저작=claude / Q&A=solar, graceful 폴백, 게이트 provider 무관. */
import { describe, expect, it } from "vitest";

import { resolveProviderName, taskDefaultProvider } from "../src/services/ai/gateway.js";
import { appFor, postJson, readSse, withServer } from "./util.js";

const withApp = <T>(fn: (base: string) => Promise<T>): Promise<T> => withServer(appFor(), fn);

describe("g3.1 태스크 기본 provider 정책", () => {
  it("기본값: 저작=claude · Q&A=solar", () => {
    expect(taskDefaultProvider("authoring")).toBe("claude");
    expect(taskDefaultProvider("qa")).toBe("solar");
  });

  it("graceful 폴백: 저작 claude 키 없으면 solar → 그것도 없으면 mock (실패 금지)", () => {
    // claude 선호 + anthropic 키 존재 → claude
    expect(resolveProviderName("claude", { anthropic: true, solar: true }, false)).toBe("claude");
    // claude 선호 + anthropic 키 없음 + solar 있음 → solar 폴백
    expect(resolveProviderName("claude", { anthropic: false, solar: true }, false)).toBe("solar");
    // 키 하나도 없음 → mock (끝까지 동작)
    expect(resolveProviderName("claude", {}, false)).toBe("mock");
  });

  it("Q&A solar 폴백: solar 키 없으면 claude → mock", () => {
    expect(resolveProviderName("solar", { solar: true }, false)).toBe("solar");
    expect(resolveProviderName("solar", { solar: false, anthropic: true }, false)).toBe("claude");
    expect(resolveProviderName("solar", {}, false)).toBe("mock");
  });

  it("mock 모드면 선호·키 무관하게 mock (그레이스풀)", () => {
    expect(resolveProviderName("claude", { anthropic: true }, true)).toBe("mock");
    expect(resolveProviderName("solar", { solar: true }, true)).toBe("mock");
  });
});

describe("g3.1 라우트 — 태스크 정책 하에서도 동작 불변", () => {
  it("저작 추출(기본, provider 미지정): 정상 스트림 · SSE 계약 유지", async () => {
    await withApp(async (base) => {
      const events = await readSse(base, "/api/v1/extraction/stream", { text: "겨울철 저온에서 고무 블레이드는 소음이 발생한다" });
      expect(events[0].event).toBe("status"); // 첫 status(=provider)
      expect(events.at(-1)?.event).toBe("done");
      const v = events.find((e) => e.event === "validation")!;
      expect(v.data.conforms).toBe(true); // 인과 프레임 저장 가능
    });
  });

  it("Q&A(기본=solar): 정상 응답", async () => {
    await withApp(async (base) => {
      const { status, body } = await postJson(base, "/api/v1/qa", { question: "중형 SUV 안전 길이는?", mode: "verified" });
      expect(status).toBe(200);
      const b = body as { layer?: string; verified_answer?: { determinism?: string } };
      expect(b.layer).toBe("A");
      expect(b.verified_answer?.determinism).toBe("sparql"); // 결정론 경로 — provider 정책과 무관
    });
  });

  it("안전 불변: save 서버 재검증은 provider 를 받지 않는다 → range 위반이면 provider 무관 409", async () => {
    await withApp(async (base) => {
      const { status } = await postJson(base, "/api/v1/extraction/save", {
        sentence_text: "경도가 겨울철을 유발한다",
        category: "소음",
        approved: true,
        concepts: [{ label: "경도", type: "Attribute" }, { label: "겨울철", type: "EnvCondition" }],
        relations: [{ subject: "경도", predicate: "causes", object: "겨울철" }],
      });
      expect(status).toBe(409); // 결정론 검증 — provider 정책과 무관
    });
  });
});
