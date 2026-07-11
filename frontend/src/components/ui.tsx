/** 공용 UI 프리미티브 — 위반 표시·에러 안내·출처·배지. */
import type { ReactNode } from "react";

import type { Violation, Source } from "../types/contracts";

export function Card({ title, children, tone = "plain" }: { title?: ReactNode; children: ReactNode; tone?: "plain" | "ok" | "bad" | "warn" }) {
  const border = tone === "ok" ? "border-emerald-300" : tone === "bad" ? "border-rose-300" : tone === "warn" ? "border-amber-300" : "border-slate-200";
  const head = tone === "ok" ? "text-emerald-700" : tone === "bad" ? "text-rose-700" : tone === "warn" ? "text-amber-700" : "text-slate-700";
  return (
    <section className={`rounded-lg border ${border} bg-white shadow-sm`}>
      {title && <header className={`px-4 py-2.5 border-b border-slate-100 font-semibold text-sm ${head}`}>{title}</header>}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Chip({ children, color = "slate" }: { children: ReactNode; color?: string }) {
  const map: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700 border-slate-200",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
    amber: "bg-amber-50 text-amber-800 border-amber-300",
    rose: "bg-rose-50 text-rose-700 border-rose-200",
    violet: "bg-violet-50 text-violet-700 border-violet-200",
  };
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${map[color] ?? map.slate}`}>{children}</span>;
}

/** CD-7: severity=violation 은 amber, 저장 차단 신호. warning 은 정보 표시. */
export function ViolationList({ violations }: { violations: Violation[] }) {
  if (!violations.length) return null;
  return (
    <ul className="space-y-2">
      {violations.map((v, i) => {
        const isViolation = v.severity === "violation";
        return (
          <li key={i} className={`rounded-md border p-3 text-sm ${isViolation ? "border-amber-400 bg-amber-50" : "border-slate-200 bg-slate-50"}`}>
            <div className="flex items-center gap-2 mb-1">
              <Chip color={isViolation ? "amber" : "slate"}>{isViolation ? "⚠ 위반 (저장 차단)" : "ⓘ 경고"}</Chip>
              <span className="text-xs text-slate-500">{v.code}{v.sentence ? ` · ${v.sentence}` : ""}{v.source_shape ? ` · ${v.source_shape}` : ""}</span>
            </div>
            <p className={isViolation ? "text-amber-900" : "text-slate-700"}>{v.message}</p>
          </li>
        );
      })}
    </ul>
  );
}

/** 에러 UX: user_message + 다음 행동 버튼. 에러 코드/스택 노출 금지. */
export function ErrorNotice({ message, actionLabel, onAction }: { message: string; actionLabel?: string; onAction?: () => void }) {
  return (
    <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 flex items-center justify-between gap-3">
      <span>{message}</span>
      {onAction && (
        <button onClick={onAction} className="shrink-0 rounded-md bg-rose-600 px-3 py-1.5 text-white text-xs font-medium hover:bg-rose-700">
          {actionLabel ?? "다시 시도"}
        </button>
      )}
    </div>
  );
}

/** 출처(문장·규칙·IRI) — 답변 구조 §6 의 마지막 블록. */
export function SourceList({ sources }: { sources: Source[] }) {
  if (!sources.length) return <p className="text-sm text-slate-400">출처 없음</p>;
  return (
    <ul className="space-y-1.5">
      {sources.map((s, i) => (
        <li key={i} className="text-sm flex items-start gap-2">
          <Chip color={s.rule ? "violet" : "blue"}>{s.rule ? `규칙 ${s.rule}` : `문장 ${s.sentence}`}</Chip>
          <span className="text-slate-600">
            {s.text ? s.text : <span className="font-mono text-xs text-slate-400">{s.iri}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Button({ children, onClick, disabled, variant = "primary", title, type = "button" }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean; variant?: "primary" | "ghost" | "danger"; title?: string; type?: "button" | "submit";
}) {
  const base = "rounded-md px-4 py-2 text-sm font-medium transition disabled:opacity-40 disabled:cursor-not-allowed";
  const map = {
    primary: "bg-slate-900 text-white hover:bg-slate-700",
    ghost: "border border-slate-300 text-slate-700 hover:bg-slate-100",
    danger: "bg-rose-600 text-white hover:bg-rose-700",
  };
  return <button type={type} title={title} onClick={onClick} disabled={disabled} className={`${base} ${map[variant]}`}>{children}</button>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-500">
      <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
      {label}
    </span>
  );
}
