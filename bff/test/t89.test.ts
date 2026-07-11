/** T-89 — OOV 트리아지 엔드포인트. 매핑 후보·provenance·provisional(fail-closed). */
import { describe, expect, it } from "vitest";

import { appFor, postJson, withServer } from "./util.js";

const withApp = <T>(fn: (base: string) => Promise<T>): Promise<T> => withServer(appFor(), fn);

describe("T-89 OOV 트리아지", () => {
  it("표기 이형 → 매핑 후보 + altLabel 제안 + provisional + provenance", async () => {
    await withApp(async (base) => {
      const { status, body } = await postJson(base, "/api/v1/oov/triage", {
        label: "블레이드는", sentence: "겨울철…", project_id: "mvp",
      });
      expect(status).toBe(200);
      const b = body as {
        triage: string; candidates: unknown[]; provisional: boolean;
        provenance: { project_id: string | null }; admin_proposal: { status: string };
      };
      expect(b.triage).toBe("synonym_variant");
      expect(b.candidates.length).toBeGreaterThan(0);
      expect(b.provisional).toBe(true); // fail-closed: 접지 미사용
      expect(b.provenance.project_id).toBe("mvp");
      expect(b.admin_proposal.status).toBe("stub");
    });
  });

  it("범위 밖 용어 → 후보 없음(정당한 거부)", async () => {
    await withApp(async (base) => {
      const { body } = await postJson(base, "/api/v1/oov/triage", { label: "자전거 체인" });
      const b = body as { triage: string; candidates: unknown[] };
      expect(b.triage).toBe("out_of_scope");
      expect(b.candidates).toEqual([]);
    });
  });
});
