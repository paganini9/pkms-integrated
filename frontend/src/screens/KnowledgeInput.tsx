/** SC-1 지식 입력 (FR-01~03) — SSE 스트리밍 → 검증 → HITL 승인 저장 → 파생 읽기전용 요약. */
import { useRef, useState } from "react";

import { api, ApiCallError } from "../api/client";
import type { StreamController, ABExtractResponse, OovTriageResponse } from "../api/types";
import { Button, Card, Chip, ErrorNotice, Spinner, ViolationList } from "../components/ui";
import { useApp } from "../store";
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
  // T-90 — 저작 provider 선택(세션) + A/B diff
  const { authorProvider, setAuthorProvider, project } = useApp();
  const [ab, setAb] = useState<ABExtractResponse | null>(null);
  const [abLoading, setAbLoading] = useState(false);
  const [triage, setTriage] = useState<OovTriageResponse[]>([]); // T-89 OOV 트리아지

  // CD-7: severity=violation 이 하나라도 있으면 저장 차단
  const hasBlocking = violations.some((v) => v.severity === "violation");

  function reset() {
    setConcepts([]); setRelations([]); setViolations([]); setConforms(null);
    setDraftId(null); setError(null); setSaved(null); setApproved(false); setSaveError(null); setTriage([]);
  }

  function start() {
    ctrl.current?.cancel();
    reset();
    setPhase("streaming");
    setStatusMsg("연결 중…");
    ctrl.current = api.extractionStream({ text, provider: authorProvider }, {
      onStatus: (d) =>
        setStatusMsg(
          d.stage === "provider"
            ? d.fallback ? `${d.msg}` : `provider: ${d.provider}`
            : (d.msg ?? d.stage),
        ),
      onConcept: (c) => setConcepts((p) => [...p, c]),
      onRelation: (r) => setRelations((p) => [...p, r]),
      onValidation: (d) => {
        setConforms(d.conforms); setViolations(d.violations);
        // T-89 — 온톨로지 밖(unknown_concept) 개념은 막기만 하지 않고 매핑 후보를 트리아지한다.
        const oov = [...new Set(d.violations.filter((v) => v.code === "unknown_concept").map((v) => v.offender))];
        setTriage([]);
        oov.forEach(async (label) => {
          try {
            const t = await api.oovTriage({ label, sentence: text, project_id: project?.id });
            setTriage((p) => [...p, t]);
          } catch { /* 트리아지 실패는 저작을 막지 않는다 */ }
        });
      },
      onDone: (d) => { setDraftId(d.draft_id); setPhase("done"); setStatusMsg(""); },
      // §5: error 수신 시 렌더 유지 + 다시 시도. 자동 재연결 금지.
      onError: (e) => { setError(e.user_message); setPhase("error"); setStatusMsg(""); },
    });
  }

  async function runAB() {
    setAb(null); setAbLoading(true);
    try {
      setAb(await api.extractionAB({ text }));
    } catch {
      setAb(null);
    } finally {
      setAbLoading(false);
    }
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
        {/* T-90 — 추출 모델 선택. Solar 기본(무료), Claude 옵션(유료·명시 opt-in). */}
        <div className="mt-3 flex items-center gap-2 text-xs">
          <span className="text-slate-500">추출 모델</span>
          <div className="inline-flex rounded-md border border-slate-300 overflow-hidden">
            <button
              onClick={() => setAuthorProvider("solar")}
              className={`px-2.5 py-1 ${authorProvider === "solar" ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}
            >Solar <span className="opacity-70">· 무료</span></button>
            <button
              onClick={() => setAuthorProvider("claude")}
              className={`px-2.5 py-1 border-l border-slate-300 ${authorProvider === "claude" ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}
              title="Claude 는 옵션(유료)입니다. 복합어 분해·지시준수가 강할 수 있으나 비용이 발생합니다."
            >Claude <span className="opacity-70">· 옵션·유료</span></button>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <Button onClick={start} disabled={phase === "streaming" || !text.trim()}>
            {phase === "streaming" ? "추출 중…" : "추출 시작"}
          </Button>
          <Button variant="ghost" onClick={runAB} disabled={abLoading || !text.trim()} title="Solar·Claude 두 모델로 추출해 개념·관계를 나란히 비교합니다.">
            {abLoading ? "두 모델 추출 중…" : "두 모델로 추출 (A/B)"}
          </Button>
          <Button variant="ghost" onClick={() => { setText(SAMPLE_OK); }}>정상 예시</Button>
          <Button variant="ghost" onClick={() => { setText(SAMPLE_BAD); }}>위반 예시(CD-7)</Button>
          {phase === "streaming" && <Spinner label={statusMsg} />}
        </div>
      </Card>

      {ab && <ABDiff ab={ab} />}

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

      {triage.length > 0 && <OovTriage triage={triage} />}

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

/** T-89 — OOV 트리아지. 온톨로지 밖 개념을 막기만 하지 않고 매핑 후보·제안을 보인다(provisional). */
function OovTriage({ triage }: { triage: OovTriageResponse[] }) {
  return (
    <Card title="용어 트리아지 (온톨로지 밖 개념)">
      <p className="text-xs text-slate-500 mb-3">
        아래 용어는 온톨로지에 없어 접지에 쓰이지 않습니다(안전). 매핑 후보가 있으면 관리자 편입을 제안하고,
        범위 밖이면 정당하게 거부합니다. 이 상태로는 저장돼도 해당 개념은 provisional 입니다.
      </p>
      <div className="space-y-2">
        {triage.map((t, i) => (
          <div key={i} className="rounded-md border border-slate-200 p-3">
            <div className="flex items-center gap-2 flex-wrap">
              <Chip color={t.candidates.length > 0 ? "amber" : "slate"}>{t.label}</Chip>
              <span className="text-xs text-slate-500">
                {t.triage === "synonym_variant" ? "어휘 변이 — 매핑 후보" : "범위 밖 — 정당한 거부"}
              </span>
              {t.provisional && <span className="text-xs text-slate-400">provisional</span>}
            </div>
            {t.candidates.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5 items-center">
                <span className="text-xs text-slate-500">후보:</span>
                {t.candidates.map((c, j) => (
                  <Chip key={j} color="blue">{c.pref_label} <span className="opacity-60">· {c.via} {c.score}</span></Chip>
                ))}
                <button className="text-xs text-blue-600 underline ml-1" title={`${t.admin_proposal.action}(스텁)`}>
                  관리자에 확장 제안
                </button>
              </div>
            ) : (
              <p className="mt-1.5 text-xs text-slate-500">{t.clarification}</p>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

/** T-90 — 두 모델 추출 A/B diff. 개념·관계를 나란히 비교(복합어 분해·인과 프레임 차이). */
function ABDiff({ ab }: { ab: ABExtractResponse }) {
  return (
    <Card title="A/B — 두 모델 추출 비교">
      <p className="text-xs text-slate-500 mb-3">
        같은 문장을 두 모델로 추출한 결과입니다. 검증·저장 게이트는 모델과 무관하게 동일하게 적용됩니다(결정론 우선).
        복합어를 분해했는지, 인과 관계를 어떻게 잡았는지 비교하세요.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {ab.results.map((r, i) => (
          <div key={i} className="rounded-md border border-slate-200 p-3">
            <div className="flex items-center gap-2 mb-2">
              <Chip color={r.requested_provider === "claude" ? "violet" : "blue"}>{r.requested_provider}</Chip>
              {r.actual_provider !== r.requested_provider && (
                <span className="text-xs text-amber-700">→ {r.actual_provider} 폴백(키 없음)</span>
              )}
              {r.requested_provider === "claude" && <span className="text-xs text-slate-400">유료</span>}
              {r.error && <span className="text-xs text-red-600">오류: {r.error}</span>}
            </div>
            <p className="text-xs text-slate-500">개념 ({r.concepts.length})</p>
            <div className="flex flex-wrap gap-1.5 mb-2 min-h-[1.5rem]">
              {r.concepts.map((c, j) => <Chip key={j} color="blue">{c.label} · {c.type}</Chip>)}
              {r.concepts.length === 0 && <span className="text-xs text-slate-400">없음</span>}
            </div>
            <p className="text-xs text-slate-500">관계 ({r.relations.length})</p>
            <ul className="min-h-[1.5rem]">
              {r.relations.map((rel, j) => (
                <li key={j} className="text-xs font-mono text-slate-700">{rel.subject} —{rel.predicate}→ {rel.object}</li>
              ))}
              {r.relations.length === 0 && <span className="text-xs text-slate-400">없음</span>}
            </ul>
          </div>
        ))}
      </div>
    </Card>
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
