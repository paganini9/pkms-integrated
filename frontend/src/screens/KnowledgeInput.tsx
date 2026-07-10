/** SC-1 지식 입력 (FR-01~03) — SSE 스트리밍 → 검증 → HITL 승인 저장 → 파생 읽기전용 요약. */
import { useRef, useState } from "react";

import { api, ApiCallError } from "../api/client";
import type { StreamController } from "../api/types";
import { Button, Card, Chip, ErrorNotice, Spinner, ViolationList } from "../components/ui";
import type { Concept, Relation, Violation, SaveResponse } from "../types/contracts";

type Phase = "idle" | "streaming" | "done" | "error";

const SAMPLE_OK = "겨울철 저온에서 고무 블레이드는 소음이 발생한다";
const SAMPLE_BAD = "경도가 상승하면 겨울철을 유발한다"; // causes 치역 위반 예시 (CD-7)

export default function KnowledgeInput() {
  const [text, setText] = useState(SAMPLE_OK);
  const [phase, setPhase] = useState<Phase>("idle");
  const [statusMsg, setStatusMsg] = useState("");
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [relations, setRelations] = useState<Relation[]>([]);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [conforms, setConforms] = useState<boolean | null>(null);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState("소음");
  const [approved, setApproved] = useState(false);
  const [saved, setSaved] = useState<SaveResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const ctrl = useRef<StreamController | null>(null);

  // CD-7: severity=violation 이 하나라도 있으면 저장 차단
  const hasBlocking = violations.some((v) => v.severity === "violation");

  function reset() {
    setConcepts([]); setRelations([]); setViolations([]); setConforms(null);
    setDraftId(null); setError(null); setSaved(null); setApproved(false); setSaveError(null);
  }

  function start() {
    ctrl.current?.cancel();
    reset();
    setPhase("streaming");
    setStatusMsg("연결 중…");
    ctrl.current = api.extractionStream({ text }, {
      onStatus: (d) => setStatusMsg(d.msg ?? d.stage),
      onConcept: (c) => setConcepts((p) => [...p, c]),
      onRelation: (r) => setRelations((p) => [...p, r]),
      onValidation: (d) => { setConforms(d.conforms); setViolations(d.violations); },
      onDone: (d) => { setDraftId(d.draft_id); setPhase("done"); setStatusMsg(""); },
      // §5: error 수신 시 렌더 유지 + 다시 시도. 자동 재연결 금지.
      onError: (e) => { setError(e.user_message); setPhase("error"); setStatusMsg(""); },
    });
  }

  async function save() {
    setSaving(true); setSaveError(null);
    try {
      const res = await api.extractionSave({
        sentence_text: text, concepts, relations, category, approved: true, draft_id: draftId ?? undefined,
      });
      setSaved(res);
    } catch (e) {
      setSaveError(e instanceof ApiCallError ? e.body.user_message : "저장에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold">지식 입력</h1>
        <p className="text-sm text-slate-500 mt-1">자연어 문장이 진실원입니다. 규칙·SHACL 은 저장 시 자동 파생되며 직접 편집하지 않습니다(수정은 문장을 고쳐 재파생).</p>
      </div>

      <Card>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="예: 겨울철 저온에서 고무 블레이드는 소음이 발생한다"
          className="w-full rounded-md border border-slate-300 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
        />
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <Button onClick={start} disabled={phase === "streaming" || !text.trim()}>
            {phase === "streaming" ? "추출 중…" : "추출 시작"}
          </Button>
          <Button variant="ghost" onClick={() => { setText(SAMPLE_OK); }}>정상 예시</Button>
          <Button variant="ghost" onClick={() => { setText(SAMPLE_BAD); }}>위반 예시(CD-7)</Button>
          {phase === "streaming" && <Spinner label={statusMsg} />}
        </div>
      </Card>

      {(concepts.length > 0 || relations.length > 0 || phase !== "idle") && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <Card title={`개념 (${concepts.length})`}>
            <div className="flex flex-wrap gap-2 min-h-[2rem]">
              {concepts.map((c, i) => (
                <Chip key={i} color="blue">{c.label} · {c.type}</Chip>
              ))}
              {phase === "streaming" && concepts.length === 0 && <span className="text-sm text-slate-400">추출 대기…</span>}
            </div>
          </Card>
          <Card title={`관계 (${relations.length})`}>
            <ul className="space-y-1.5 min-h-[2rem]">
              {relations.map((r, i) => (
                <li key={i} className="text-sm">
                  <span className="font-medium">{r.subject}</span>
                  <span className="mx-1.5 text-violet-600 font-mono text-xs">—{r.predicate}→</span>
                  <span className="font-medium">{r.object}</span>
                  {r.confidence != null && <span className="ml-2 text-xs text-slate-400">({Math.round(r.confidence * 100)}%)</span>}
                </li>
              ))}
              {phase === "streaming" && relations.length === 0 && <span className="text-sm text-slate-400">추출 대기…</span>}
            </ul>
          </Card>
        </div>
      )}

      {phase === "error" && error && (
        <ErrorNotice message={error} actionLabel="다시 시도" onAction={start} />
      )}

      {conforms !== null && (
        <Card title="명세 검증" tone={hasBlocking ? "warn" : "ok"}>
          {conforms && violations.length === 0 ? (
            <p className="text-sm text-emerald-700">✓ 명세 위반 없음 — 저장할 수 있습니다.</p>
          ) : (
            <div className="space-y-3">
              {hasBlocking && (
                <p className="text-sm text-amber-800 font-medium">amber 위반이 있어 저장이 차단됩니다. 문장을 수정해 다시 추출하세요(직접 편집 없음).</p>
              )}
              <ViolationList violations={violations} />
            </div>
          )}
        </Card>
      )}

      {phase === "done" && !saved && (
        <Card title="저장 (HITL 승인)">
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm">
              <span className="text-slate-600">카테고리</span>
              <input value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-md border border-slate-300 px-2 py-1 text-sm w-32" />
            </label>
            <label className={`flex items-center gap-2 text-sm ${hasBlocking ? "opacity-50" : ""}`}>
              <input type="checkbox" checked={approved} disabled={hasBlocking} onChange={(e) => setApproved(e.target.checked)} />
              <span>추출 결과를 검토했으며 저장을 승인합니다.</span>
            </label>
            <div className="flex items-center gap-3">
              <Button
                onClick={save}
                disabled={hasBlocking || !approved || saving}
                title={hasBlocking ? "amber 위반을 먼저 해소하세요 (CD-7)" : !approved ? "승인 체크가 필요합니다" : undefined}
              >
                {saving ? "저장 중…" : "승인 후 저장"}
              </Button>
              {hasBlocking && <span className="text-xs text-amber-700">저장 버튼은 위반이 해소되어야 활성화됩니다.</span>}
            </div>
            {saveError && <ErrorNotice message={saveError} actionLabel="다시 시도" onAction={save} />}
          </div>
        </Card>
      )}

      {saved && <DerivedSummary saved={saved} />}
    </div>
  );
}

/** 저장 후 파생물(규칙·SHACL·인과엣지) — 읽기 전용 요약 (FR-3d). */
function DerivedSummary({ saved }: { saved: SaveResponse }) {
  const { sentence, derived, human_view } = saved;
  return (
    <Card title="✓ 저장 완료 — 파생 요약 (읽기 전용)" tone="ok">
      <div className="space-y-4 text-sm">
        <div>
          <span className="text-slate-500">문장 </span>
          <Chip color="emerald">{sentence.id}</Chip>
          <p className="mt-1 text-slate-800">{sentence.text}</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <Chip>카테고리 {sentence.category}</Chip>
            <Chip>증상 {sentence.about_symptom}</Chip>
            <Chip>극성 {sentence.polarity}</Chip>
            {sentence.mentions.map((m) => <Chip key={m} color="blue">{m}</Chip>)}
          </div>
        </div>
        <div className="border-t border-slate-100 pt-3">
          <p className="text-slate-500 mb-1">파생 규칙 <span className="text-xs">(문장에서 자동 생성 · 직접 편집 불가)</span></p>
          <div className="rounded-md bg-slate-50 border border-slate-200 p-3">
            <p className="font-medium">{derived.rule.label} <Chip color="violet">{derived.rule.id}</Chip></p>
            <ul className="mt-1.5 text-xs text-slate-600 space-y-0.5">
              {derived.rule.conds.map((c, i) => <li key={i} className="font-mono">{c.path} {c.op} {c.val}</li>)}
            </ul>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <p className="text-slate-500 mb-1">SHACL 게이트</p>
            {derived.shapes.map((s) => (
              <div key={s.id} className="text-xs rounded bg-slate-50 border border-slate-200 px-2 py-1 mb-1">
                {s.id} → gate_for {s.gate_for} <span className="text-slate-400">({s.sentence})</span>
              </div>
            ))}
          </div>
          <div>
            <p className="text-slate-500 mb-1">인과 엣지</p>
            {derived.causal_edges.map((e, i) => (
              <div key={i} className="text-xs rounded bg-slate-50 border border-slate-200 px-2 py-1 mb-1 font-mono">
                {e.subject} —{e.predicate}→ {e.object}
              </div>
            ))}
          </div>
        </div>
        {human_view.length > 0 && (
          <div className="border-t border-slate-100 pt-3">
            <p className="text-slate-500 mb-1">사람용 요약</p>
            {human_view.map((h, i) => <p key={i} className="font-mono text-xs text-slate-700">{h}</p>)}
          </div>
        )}
      </div>
    </Card>
  );
}
