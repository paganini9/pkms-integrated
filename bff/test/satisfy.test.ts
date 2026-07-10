import { describe, expect, it } from "vitest";

import { appFor, postJson, withServer } from "./util.js";

const design = {
  bad: { id: "Blade_bad", material: "Rubber", length_mm: 600, spring_n: 8, arm_shape: "simple", vehicle: "MidSizeSUV", env: "Winter" },
  good: { id: "Blade_good", material: "Silicone", length_mm: 550, spring_n: 12, arm_shape: "complex", vehicle: "CompactSedan", env: "Winter" },
  pending: { material: "Rubber", length_mm: 600, arm_shape: "simple", vehicle: "MidSizeSUV", env: "Winter" },
};

describe("T-52 /satisfy — 무변형 통과 (CD-1)", () => {
  it("satisfy_good: 실리콘 설계 → satisfies true, violations []", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await postJson(base, "/api/v1/satisfy", {
        project_id: "proj-winter-suv",
        design: design.good,
        require: ["RB_Winter", "RB_NoChatter"],
      });
      expect(status).toBe(200);
      expect(body.satisfies).toBe(true);
      expect(body.violations).toEqual([]);
      expect(body.applied_categories).toEqual(["소음", "떨림"]);
    });
  });

  it("satisfy_bad: 고무 설계 → satisfies false, CD-1 정규화(violations vs violation_bases)", async () => {
    await withServer(appFor(), async (base) => {
      const { body } = await postJson(base, "/api/v1/satisfy", {
        project_id: "proj-winter-suv",
        design: design.bad,
        require: ["RB_Winter", "RB_NoChatter"],
      });
      expect(body.satisfies).toBe(false);
      expect(body.violations).toEqual(["S1", "S3", "S4", "S6"]);
      expect(body.violation_bases).toEqual(["S1", "S3,S5", "S4", "S6"]);
    });
  });

  it("satisfy_pending_missing: spring_n 결측 → 200, satisfies null, pending_reason (CD-8)", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await postJson(base, "/api/v1/satisfy", {
        project_id: "proj-winter-suv",
        design: design.pending,
      });
      expect(status).toBe(200);
      expect(body.satisfies).toBeNull();
      expect(body.pending_reason).toBe("missing_required");
    });
  });

  it("satisfy_scope_B: 카테고리 [떨림] → 소음 규칙 미적용, 3 위반", async () => {
    await withServer(appFor(), async (base) => {
      const { body } = await postJson(base, "/api/v1/satisfy", {
        project_id: "proj-vibration-lab",
        design: { ...design.bad },
        require: ["RB_NoChatter"],
        categories: ["떨림"],
      });
      expect(body.satisfies).toBe(false);
      expect(body.violations).toEqual(["S3", "S4", "S6"]);
      expect(body.applied_categories).toEqual(["떨림"]);
    });
  });

  it("CD-6: X-Trace-Id 전파 — 응답 trace_id 가 요청값과 일치", async () => {
    await withServer(appFor(), async (base) => {
      const { body } = await postJson(
        base,
        "/api/v1/satisfy",
        { project_id: "p", design: design.good, require: [] },
        { "X-Trace-Id": "trace-xyz-123" },
      );
      expect(body.trace_id).toBe("trace-xyz-123");
    });
  });
});
