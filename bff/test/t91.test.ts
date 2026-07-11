/** T-91 — 인과 프레임: 조건은 증상 앵커(증상 conditionedOn 조건), 부품 앵커 금지.
 *
 * 이슈2(b): '겨울철 저온에서 고무 블레이드는 소음이 발생한다' 를 이항으로 쪼갤 때 조건을 부품에 걸면
 * (블레이드 conditionedOn 겨울) conditionedOn 도메인(FailureBehavior) 위반 → 저장 차단이었다.
 * 프레임이 조건을 **증상**에 걸면(소음 conditionedOn 겨울) 위반이 사라지고, 지식서비스가
 * (기전·조건·증상)을 한 Causation 노드로 재화할 수 있다.
 */
import { describe, expect, it } from "vitest";

import { appFor, readSse, withServer } from "./util.js";

const FAILING = "겨울철 저온에서 고무 블레이드는 소음이 발생한다";
const SYMPTOMS = new Set(["소음", "Noise", "떨림", "TipChatter"]);

describe("T-91 인과 프레임(증상 앵커 조건)", () => {
  it("실패 문장: 조건은 증상에 걸리고, 부품 주어 conditionedOn 은 없다 → 검증 통과", async () => {
    await withServer(appFor(), async (base) => {
      const events = await readSse(base, "/api/v1/extraction/stream", { text: FAILING });
      const relations = events
        .filter((e) => e.event === "relation")
        .map((e) => e.data as { subject: string; predicate: string; object: string });

      const conditioned = relations.filter((r) => r.predicate === "conditionedOn");
      expect(conditioned.length).toBeGreaterThan(0);
      // 모든 conditionedOn 의 주어는 증상이어야 한다(부품·재질 앵커 금지).
      for (const r of conditioned) {
        expect(SYMPTOMS.has(r.subject)).toBe(true);
      }
      // 원인(재질)은 causes 로 증상에 걸린다 — (기전·조건·증상) 묶임의 근거.
      expect(relations.some((r) => r.predicate === "causes" && SYMPTOMS.has(r.object))).toBe(true);

      // 프레임이 맞으면 명세 검증이 통과(저장 가능)한다.
      const v = events.find((e) => e.event === "validation")!;
      expect(v.data.conforms).toBe(true);
    });
  });
});
