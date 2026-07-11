import { describe, expect, it } from "vitest";

import { appFor, delJson, getJson, postJson, withServer } from "./util.js";

const ADMIN = { "X-Role": "admin" };

describe("T-54 관리자 표면 — 역할 게이트 (CD-5)", () => {
  it("음성: 비관리자 GET /governance/concepts → 403 FORBIDDEN", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await getJson(base, "/api/v1/governance/concepts");
      expect(status).toBe(403);
      expect(body.code).toBe("FORBIDDEN");
    });
  });

  it("비관리자 헤더 없음 → engineer 로 간주 → 403", async () => {
    await withServer(appFor(), async (base) => {
      const { status } = await getJson(base, "/api/v1/rules");
      expect(status).toBe(403);
    });
  });

  it("admin GET /governance/concepts → 200 builtin/custom", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await getJson(base, "/api/v1/governance/concepts", ADMIN);
      expect(status).toBe(200);
      expect(Array.isArray(body.builtin)).toBe(true);
      expect(Array.isArray(body.custom)).toBe(true);
    });
  });

  it("admin DELETE builtin 개념 → 400 BUILTIN_LOCKED (AC-8, 지식서비스 판정 통과)", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await delJson(base, "/api/v1/governance/concepts/Symptom", ADMIN);
      expect(status).toBe(400);
      expect(body.code).toBe("BUILTIN_LOCKED");
    });
  });

  it("admin DELETE custom 개념 → 200", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await delJson(base, "/api/v1/governance/concepts/Vibration", ADMIN);
      expect(status).toBe(200);
      expect(body.deleted).toBe(true);
    });
  });

  it("admin POST /upper-ontology/classes — approved 없으면 409, 있으면 200", async () => {
    await withServer(appFor(), async (base) => {
      const blocked = await postJson(base, "/api/v1/upper-ontology/classes", { changes: [] }, ADMIN);
      expect(blocked.status).toBe(409);
      expect(blocked.body.code).toBe("GUARDRAIL_BLOCKED");

      const ok = await postJson(base, "/api/v1/upper-ontology/classes", { changes: [], approved: true }, ADMIN);
      expect(ok.status).toBe(200);
    });
  });

  it("admin POST /upper-ontology/consistency → 내부 reason/consistency 매핑", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await postJson(base, "/api/v1/upper-ontology/consistency", {}, ADMIN);
      expect(status).toBe(200);
      expect(body.consistent).toBe(true);
    });
  });
});

describe("조회 표면 · health", () => {
  it("GET /graph → nodes/edges/stats", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await getJson(base, "/api/v1/graph?symptom=TipChatter&sentence=S3");
      expect(status).toBe(200);
      expect(Array.isArray(body.nodes)).toBe(true);
      expect(body.stats).toBeTruthy();
      expect(body.trace_id).toBeTruthy();
    });
  });

  it("GET /dashboard → m0/m1/m2", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await getJson(base, "/api/v1/dashboard");
      expect(status).toBe(200);
      expect(body.m0).toBeTruthy();
      expect(body.m2).toBeTruthy();
    });
  });

  it("GET /health → 200, llm_provider mock, knowledge ok", async () => {
    await withServer(appFor(), async (base) => {
      const { status, body } = await getJson(base, "/api/v1/health");
      expect(status).toBe(200);
      expect(body.llm_provider).toBe("mock");
      expect((body.knowledge as Record<string, unknown>).status).toBe("ok");
    });
  });
});
