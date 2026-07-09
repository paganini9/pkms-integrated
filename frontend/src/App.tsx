/**
 * 화면 골격 (Phase 4 IA). Phase 2 에서 07 프론트엔드 Agent 가 각 화면을 채운다.
 * 엔지니어: 대시보드 · 지식입력 · 설계검증 · 지식맵 · Q&A/환각비교 · 설계비교
 * 관리자:   상위 온톨로지 · 도메인 규칙 · 거버넌스
 */
import { useEffect, useState } from "react";

import { api } from "./api/client";

export default function App() {
  const [health, setHealth] = useState<string>("확인 중…");

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(`${h.status} · LLM=${h.llm_provider}`))
      .catch((e) => setHealth(`연결 실패 — ${e.message}`));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 900, margin: "0 auto" }}>
      <h1>PKMS — 와이퍼 설계 지식관리</h1>
      <p>
        상태: <strong>{health}</strong>
      </p>

      <section>
        <h2>핵심 루프</h2>
        <ol>
          <li>SC-1 지식 입력 · 검증 · 저장 (문장이 진실원, 규칙·SHACL은 파생)</li>
          <li>SC-2 설계 검증 satisfy (정성 subsumption → SHACL·구간비교기 → 무증상 규칙)</li>
          <li>SC-3 환각비교 Q&A (LLM 단독 ‖ 온톨로지 검증답변)</li>
        </ol>
      </section>

      <p style={{ color: "#666", fontSize: "0.9rem" }}>
        G0 골격. 화면은 Phase 2 에서 채웁니다. 계약: <code>_coordination/contracts/</code>
      </p>
    </main>
  );
}
