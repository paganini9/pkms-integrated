/** S-01 대시보드 (엔지니어 홈) — 핵심 루프 진입점. */
import { Link } from "react-router-dom";

import { USING_MOCK } from "../api/client";
import { Card, Chip } from "../components/ui";

const loop = [
  { to: "/input", n: "SC-1", label: "지식 입력", desc: "자연어 → SSE 추출 → 검증 → HITL 저장 → 파생 요약" },
  { to: "/requirements", n: "SC-1P", label: "프로젝트 요구", desc: "자연어 → RequiredBehavior 파싱" },
  { to: "/verify", n: "SC-2", label: "설계 검증", desc: "satisfy 3단계 · 위반·대안·판정보류" },
  { to: "/qa", n: "SC-3", label: "Q&A · 환각비교", desc: "검증 답변 ‖ LLM 단독(미검증)" },
  { to: "/map", n: "SC-4", label: "지식맵", desc: "inferred 점선 · 출처 추적" },
];

export default function Dashboard() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold">대시보드</h1>
        <p className="text-sm text-slate-500 mt-1">지식이 얼마나 쌓였고 얼마나 건강한가 — 핵심 루프의 진입점입니다.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[["M0 상위", "18 클래스"], ["M1 규칙", "5 규칙 · 6 문장"], ["M2 인스턴스", "2 설계"], ["검증", "위반 4"]].map(([k, v]) => (
          <div key={k} className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">{k}</p>
            <p className="mt-1 font-bold text-slate-800">{v}</p>
          </div>
        ))}
      </div>

      <Card title="핵심 루프">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {loop.map((s) => (
            <Link key={s.to} to={s.to} className="block rounded-md border border-slate-200 p-3 hover:border-slate-400 hover:bg-slate-50 transition">
              <div className="flex items-center gap-2">
                <Chip color="blue">{s.n}</Chip><span className="font-medium text-sm">{s.label}</span>
              </div>
              <p className="mt-1 text-xs text-slate-500">{s.desc}</p>
            </Link>
          ))}
        </div>
      </Card>

      <p className="text-xs text-slate-400">
        {USING_MOCK ? "Mock 모드로 동작 중입니다. contracts/mocks fixture 를 API 경계에서 서빙합니다." : "실제 BFF API 에 연결되어 있습니다."}
      </p>
    </div>
  );
}
