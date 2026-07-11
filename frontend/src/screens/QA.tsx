/** SC-3 Q&A · 환각비교 (FR-06~09) — 검증 답변 ‖ LLM 단독(미검증) 대조. */
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiCallError } from "../api/client";
import { Button, Card, Chip, ErrorNotice, SourceList, Spinner } from "../components/ui";
import { useApp } from "../store";
import type { QaResponse } from "../types/contracts";

const SAMPLES = [
  "중형 SUV에 고무 600mm 써도 될까?",
  "중형 SUV 안전 길이는?",
  "타이어 공기압은 몇 psi가 적정한가?",
];

export default function QA() {
  const project = useApp((s) => s.project);
  const [question, setQuestion] = useState<string>(SAMPLES[0]!);
  const [mode, setMode] = useState<"compare" | "verified">("compare");
  const [result, setResult] = useState<QaResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask() {
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await api.qa({ question, mode, ...(project ? { project_id: project.id } : {}) });
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiCallError ? e.body.user_message : "응답에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold">Q&A · 환각비교</h1>
        <p className="text-sm text-slate-500 mt-1">왼쪽은 검증 전 LLM 원답변입니다. 오른쪽은 온톨로지·명세로 검증된 답변입니다.</p>
      </div>

      <Card>
        <textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={2}
          className="w-full rounded-md border border-slate-300 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400" />
        <div className="mt-3 flex items-center gap-3 flex-wrap">
          <div className="inline-flex rounded-md border border-slate-300 overflow-hidden text-sm">
            <button onClick={() => setMode("compare")} className={`px-3 py-1.5 ${mode === "compare" ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}>비교 (환각 대조)</button>
            <button onClick={() => setMode("verified")} className={`px-3 py-1.5 ${mode === "verified" ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}>검증만</button>
          </div>
          <Button onClick={ask} disabled={loading || !question.trim()}>{loading ? "질의 중…" : "질문"}</Button>
          {loading && <Spinner label="검증 경로 · LLM 경로 실행 중…" />}
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {SAMPLES.map((s) => <button key={s} onClick={() => setQuestion(s)} className="text-xs text-slate-500 hover:text-slate-800 underline">{s}</button>)}
        </div>
      </Card>

      {error && <ErrorNotice message={error} actionLabel="다시 시도" onAction={ask} />}

      {result && (
        <>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-slate-500">계층</span>
            <Chip color="blue">Layer {result.layer}</Chip>
            <span className="text-slate-400 text-xs">
              {result.layer === "A" ? "규칙질문 → SPARQL" : result.layer === "B" ? "설계검증 → satisfy" : "자유질의 → RAG"}
            </span>
          </div>

          <div className={`grid grid-cols-1 ${result.llm_answer ? "lg:grid-cols-2" : ""} gap-5`}>
            {/* LLM 단독 — 미검증. 색·라벨로 명확히 구분 */}
            {result.llm_answer && (
              <div className="rounded-lg border-2 border-dashed border-amber-400 bg-orange-50">
                <header className="px-4 py-2.5 border-b border-amber-200 flex items-center gap-2">
                  <Chip color="amber">⚠ LLM 단독 · 미검증</Chip>
                  <span className="text-xs text-amber-700">명세 검증을 거치지 않은 원답변</span>
                </header>
                <div className="p-4">
                  <p className="text-sm text-amber-900">{result.llm_answer.text}</p>
                  <p className="mt-3 text-xs text-amber-600">모델 {result.llm_answer.model} · 출처·근거 없음</p>
                </div>
              </div>
            )}

            {/* 검증 답변 — 근거 있음 */}
            <VerifiedPanel result={result} />
          </div>

          {result.comparison && result.llm_answer && <ComparisonPanel result={result} />}
        </>
      )}
    </div>
  );
}

/** 답변 구조 순서 §6: 핵심 답 → 근거(검증) → 주의 → 출처(문장·규칙). */
function VerifiedPanel({ result }: { result: QaResponse }) {
  const insufficient = result.insufficient_evidence;
  const va = result.verified_answer;
  return (
    <div className={`rounded-lg border-2 ${insufficient ? "border-slate-300 bg-slate-50" : "border-emerald-400 bg-emerald-50"}`}>
      <header className="px-4 py-2.5 border-b border-emerald-200 flex items-center gap-2">
        <Chip color={insufficient ? "slate" : "emerald"}>{insufficient ? "명세 근거 없음" : "✓ 검증 답변"}</Chip>
        <span className="text-xs text-slate-500">결정론 {va.determinism}</span>
      </header>
      <div className="p-4 space-y-3">
        {/* 1. 핵심 답 */}
        <p className={`text-sm font-medium ${insufficient ? "text-slate-700" : "text-emerald-900"}`}>{va.text}</p>

        {insufficient ? (
          // 주의: 억지 답 금지 — 지식 추가 유도 (AC-1P)
          <div className="rounded-md border border-slate-300 bg-white p-3 text-sm text-slate-600">
            이 질문에 대한 검증된 명세 근거가 없어 답변을 생성하지 않습니다.
            <Link to="/input" className="ml-1 text-blue-600 underline">지식 추가하기 →</Link>
          </div>
        ) : (
          <>
            {/* 4. 출처 (문장·규칙) */}
            <div className="border-t border-emerald-100 pt-3">
              <p className="text-xs font-semibold text-slate-500 mb-1.5">출처</p>
              <SourceList sources={va.sources} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ComparisonPanel({ result }: { result: QaResponse }) {
  const c = result.comparison!;
  return (
    <Card title="신뢰 지표 · 불일치">
      <div className="flex gap-4 mb-3 text-sm">
        <Chip color="rose">LLM 위반율 {Math.round(c.violation_rate * 100)}%</Chip>
        <Chip color="emerald">일치율 {Math.round(c.agreement_rate * 100)}%</Chip>
      </div>
      <ul className="space-y-2">
        {c.mismatches.map((m, i) => (
          <li key={i} className="text-sm rounded-md border border-rose-200 bg-rose-50 p-2.5">
            <span className="text-slate-500">주장:</span> <span className="font-medium">{m.claim}</span>
            <span className="mx-2 text-rose-400">→</span>
            <span className="text-rose-700 font-medium">{m.verdict}</span>
            {m.evidence && m.evidence.length > 0 && (
              <span className="ml-2 text-xs text-slate-500">근거 {m.evidence.map((e) => <Chip key={e} color="rose">{e}</Chip>)}</span>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
