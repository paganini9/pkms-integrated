import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { USING_MOCK } from "../api/client";
import { useApp } from "../store";

const engNav = [
  { to: "/", label: "대시보드", end: true },
  { to: "/input", label: "지식 입력" },
  { to: "/requirements", label: "프로젝트 요구" },
  { to: "/verify", label: "설계 검증" },
  { to: "/qa", label: "Q&A · 환각비교" },
  { to: "/map", label: "지식맵" },
];
const adminNav = [
  { to: "/admin/ontology", label: "상위 온톨로지" },
  { to: "/admin/rules", label: "도메인 규칙·SHACL" },
  { to: "/admin/governance", label: "거버넌스" },
];

export default function Layout() {
  const { role, setRole, health, healthError, fetchHealth } = useApp();

  useEffect(() => { fetchHealth(); }, [fetchHealth]);

  const degraded = healthError || health?.status === "degraded";
  const nav = role === "admin" ? adminNav : engNav;

  return (
    <div className="min-h-screen flex flex-col">
      {/* 상단바 */}
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-5 py-3">
        <div className="flex items-center gap-3">
          <span className="font-bold text-slate-900">PKMS</span>
          <span className="text-xs text-slate-400">와이퍼 설계 지식관리</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className={`rounded-full border px-2 py-0.5 ${USING_MOCK ? "border-violet-300 bg-violet-50 text-violet-700" : "border-emerald-300 bg-emerald-50 text-emerald-700"}`}>
            {USING_MOCK ? "Mock 모드" : "실제 API"}
          </span>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-slate-500">
            LLM={health?.llm_provider ?? "…"}
          </span>
          <div className="inline-flex rounded-md border border-slate-300 overflow-hidden">
            <button onClick={() => setRole("engineer")} className={`px-2.5 py-1 ${role === "engineer" ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}>엔지니어</button>
            <button onClick={() => setRole("admin")} className={`px-2.5 py-1 ${role === "admin" ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}>관리자</button>
          </div>
        </div>
      </header>

      {/* degraded 배너 (§4.10) */}
      {degraded && (
        <div className="bg-amber-100 border-b border-amber-300 px-5 py-2 text-sm text-amber-900">
          ⚠ 지식 서비스 연결이 불안정합니다(degraded). 일부 검증 기능이 지연되거나 Mock 폴백으로 동작할 수 있습니다.
        </div>
      )}

      <div className="flex flex-1">
        {/* 좌측 내비 */}
        <nav className="w-52 shrink-0 border-r border-slate-200 bg-white p-3 space-y-1">
          <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            {role === "admin" ? "관리자 콘솔" : "엔지니어 워크스페이스"}
          </p>
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={(n as { end?: boolean }).end}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm ${isActive ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`
              }
            >
              {n.label}
            </NavLink>
          ))}
          <p className="px-2 pt-4 text-[11px] leading-relaxed text-slate-400">
            AI 추출·응답은 명세로 검증되며, 미검증 항목은 근거 없음으로 표시됩니다.
          </p>
        </nav>

        {/* 본문 */}
        <main className="flex-1 p-6 max-w-6xl">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
