import { describe, expect, it } from "vitest";

import { appFor, postJson, withServer } from "./util.js";

describe("T-53 /qa — A/B/C 라우팅 + 환각비교", () => {
  it("qa_layerA_599: 규칙 질문 → layer A, determinism sparql, 출처 S3", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await postJson(base, "/api/v1/qa", {
        question: "중형 SUV 안전 길이는?",
        mode: "verified",
      });
      expect(status).toBe(200);
      expect(body.layer).toBe("A");
      const va = body.verified_answer as { determinism: string; sources: Array<{ sentence?: string }> };
      expect(va.determinism).toBe("sparql");
      expect(va.sources[0]?.sentence).toBe("S3");
      expect(body.insufficient_evidence).toBe(false);
      // verified 모드 → llm_answer·comparison null.
      expect(body.llm_answer).toBeNull();
      expect(body.comparison).toBeNull();
    });
  });

  it("qa_compare_suv600: 설계 검증 → layer B, determinism satisfy, 환각비교 위반", async () => {
    await withServer(appFor(), async (base) => {
      // CD-13: 날조 금지 — 확정 판정을 받으려면 질문이 재질·차종·수치를 모두 줘야 한다.
      const { body } = await postJson(base, "/api/v1/qa", {
        question: "중형 SUV에 고무 600mm 스프링 8N simple 암 써도 될까?",
        mode: "compare",
        project_id: "proj-winter-suv",
      });
      expect(body.layer).toBe("B");
      const va = body.verified_answer as { determinism: string };
      expect(va.determinism).toBe("satisfy");
      expect(body.insufficient_evidence).toBe(false);
      const llm = body.llm_answer as { text: string; model: string };
      expect(llm).not.toBeNull();
      expect(llm.model).toBe("mock");
      const cmp = body.comparison as { violation_rate: number; agreement_rate: number };
      expect(cmp).not.toBeNull();
      expect(cmp.violation_rate).toBe(1.0);
    });
  });

  it("qa_insufficient: 도메인 밖 질의 → layer C, insufficient_evidence true, 명세 근거 없음", async () => {
    await withServer(appFor(), async (base) => {
      const { body } = await postJson(base, "/api/v1/qa", {
        question: "타이어 공기압은 몇 psi가 적정한가?",
        mode: "compare",
      });
      expect(body.layer).toBe("C");
      expect(body.insufficient_evidence).toBe(true);
      const va = body.verified_answer as { text: string; sources: unknown[] };
      expect(va.text).toContain("명세 근거 없음");
      expect(va.sources).toEqual([]);
      // compare 모드지만 근거 없음 → comparison 은 검증 불가로 표기.
      expect(body.comparison).not.toBeNull();
    });
  });
});
