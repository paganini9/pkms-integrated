/** SC-2 설계 검증 (FR-04·05) — /satisfy 3단계 순서 렌더 + CD-8 판정 보류. */
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiCallError } from "../api/client";
import { Button, Card, Chip, ErrorNotice, Spinner } from "../components/ui";
import { useApp } from "../store";
import type { Design, SatisfyResponse, Step } from "../types/contracts";

const STAGE_LABEL: Record<Step["stage"], string> = {
  subsumption: "① 정성 subsumption",
  shacl_interval: "② SHACL 수치 게이트",
  symptom_free: "③ 무증상 규칙",
};
const STAGE_ORDER: Step["stage"][] = ["subsumption", "shacl_interval", "symptom_free"];

export default function DesignVerify() {
  const project = useApp((s) => s.project);
  const [design, setDesign] = useState<Design>({
    material: "Rubber", vehicle: "MidSizeSUV", length_mm: 600, spring_n: 8, arm_shape: "simple", env: "Winter",
  });
  const [omitSpring, setOmitSpring] = useState(false);
  const [result, setResult] = useState<SatisfyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof Design>(k: K, v: Design[K]) => setDesign((d) => ({ ...d, [k]: v }));

  async function run() {
    if (!project) return;
    setLoading(true); setError(null); setResult(null);
    const d: Design = { ...design };
    if (omitSpring) delete d.spring_n; // CD-8: 수치 결측 → 판정 보류 데모
    const rbs = project.requirements.map((r) => r.id);
    try {
      const res = await api.satisfy({
        project_id: project.id,
        design: d,
        // 요구 미파싱 시 require 생략 → 서버가 프로젝트의 hasRequirement 전체를 사용.
        ...(rbs.length ? { require: rbs } : {}),
        // CD-4: satisfy 게이트 컴파일 범위 = 프로젝트 지식범위. (계약 외 편의 필드로 명시 전달)
        categories: project.categories,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiCallError ? e.body.user_message : "검증에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold">설계 검증 (satisfy)</h1>
        <p className="text-sm text-slate-500 mt-1">판정은 OWL 추론 + SHACL 게이트의 결정론적 결과입니다. 프론트가 재계산하지 않습니다.</p>
      </div>

      {!project ? (
        <Card title="프로젝트 필요" tone="warn">
          <p className="text-sm text-amber-800">설계 검증은 프로젝트(요구셋·지식범위)가 있어야 동작합니다.</p>
          <p className="mt-2 text-sm"><Link to="/requirements" className="text-blue-600 underline">→ 프로젝트 요구 화면에서 프로젝트를 먼저 생성하세요</Link></p>
        </Card>
      ) : (
      <>
      <Card title={`프로젝트: ${project.name}`} tone="ok">
        <div className="text-sm flex flex-wrap items-center gap-2">
          <Chip color="blue">{project.id}</Chip>
          <span className="text-slate-500">지식범위</span>
          {project.categories.map((c) => <Chip key={c} color="violet">{c}</Chip>)}
          <span className="text-slate-500 ml-2">요구셋</span>
          {project.requirements.length
            ? project.requirements.map((r) => <Chip key={r.id} color="amber">{r.id}</Chip>)
            : <span className="text-xs text-slate-400">미파싱(서버의 전체 요구 사용)</span>}
        </div>
      </Card>

      <Card title="설계 인스턴스">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
          <Field label="재질 *">
            <select value={design.material} onChange={(e) => set("material", e.target.value as Design["material"])} className="input">
              <option value="Rubber">고무 (Rubber)</option>
              <option value="Silicone">실리콘 (Silicone)</option>
            </select>
          </Field>
          <Field label="차종 *">
            <select value={design.vehicle} onChange={(e) => set("vehicle", e.target.value as Design["vehicle"])} className="input">
              <option value="MidSizeSUV">중형 SUV</option>
              <option value="CompactSedan">소형 세단</option>
            </select>
          </Field>
          <Field label="환경">
            <select value={design.env ?? ""} onChange={(e) => set("env", (e.target.value || null) as Design["env"])} className="input">
              <option value="Winter">겨울 (Winter)</option>
              <option value="">(없음)</option>
            </select>
          </Field>
          <Field label="길이 (mm)">
            <input type="number" value={design.length_mm ?? ""} onChange={(e) => set("length_mm", e.target.value === "" ? null : Number(e.target.value))} className="input" />
          </Field>
          <Field label="스프링 (N)">
            <input type="number" disabled={omitSpring} value={omitSpring ? "" : design.spring_n ?? ""} onChange={(e) => set("spring_n", e.target.value === "" ? null : Number(e.target.value))} className="input disabled:bg-slate-100" />
          </Field>
          <Field label="암 형상">
            <select value={design.arm_shape ?? ""} onChange={(e) => set("arm_shape", (e.target.value || null) as Design["arm_shape"])} className="input">
              <option value="simple">simple</option>
              <option value="complex">complex</option>
            </select>
          </Field>
        </div>

        <div className="mt-4 space-y-2 border-t border-slate-100 pt-3">
          <label className="flex items-center gap-1.5 text-sm text-amber-800"><input type="checkbox" checked={omitSpring} onChange={(e) => setOmitSpring(e.target.checked)} /> 스프링 수치 생략 (CD-8 판정 보류 데모)</label>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <Button onClick={run} disabled={loading}>{loading ? "추론 중…" : "satisfy 실행"}</Button>
          {loading && <Spinner label="결정론 엔진 판정 중…" />}
        </div>
      </Card>

      {error && <ErrorNotice message={error} actionLabel="다시 시도" onAction={run} />}
      {result && <SatisfyResult r={result} />}
      </>
      )}

      <style>{`.input{border:1px solid #cbd5e1;border-radius:0.375rem;padding:0.375rem 0.5rem;width:100%}`}</style>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="flex flex-col gap-1"><span className="text-xs text-slate-500">{label}</span>{children}</label>;
}

function Verdict({ r }: { r: SatisfyResponse }) {
  // CD-8: satisfies===null → 판정 보류. ✅ 도 ⛔ 도 아니다.
  if (r.satisfies === null) {
    return (
      <div className="rounded-lg border-2 border-amber-300 bg-amber-50 px-4 py-3">
        <p className="font-bold text-amber-800">⏸ 판정 보류 — 수치 누락</p>
        <p className="text-sm text-amber-700 mt-1">
          {r.pending_reason === "missing_required" ? "필수 수치가 없어 확정 판정을 내릴 수 없습니다. 값을 입력하면 최종 판정이 나옵니다." : "판정을 보류합니다."}
        </p>
      </div>
    );
  }
  return r.satisfies ? (
    <div className="rounded-lg border-2 border-emerald-300 bg-emerald-50 px-4 py-3">
      <p className="font-bold text-emerald-700">✔ 만족 — 설계가 프로젝트 요구를 충족합니다.</p>
    </div>
  ) : (
    <div className="rounded-lg border-2 border-rose-300 bg-rose-50 px-4 py-3">
      <p className="font-bold text-rose-700">✘ 불만족 — 요구를 위반합니다.</p>
    </div>
  );
}

function StepView({ step }: { step: Step }) {
  const okChip = step.ok ? <Chip color="emerald">통과</Chip> : <Chip color="rose">실패</Chip>;
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="font-medium text-sm">{STAGE_LABEL[step.stage]}</span>
        {okChip}
      </div>
      {step.stage === "subsumption" && <p className="text-sm text-slate-600">{step.detail}</p>}
      {step.stage === "shacl_interval" && (
        <div className="space-y-1">
          {step.checks.map((c, i) => (
            <div key={i} className="text-sm flex items-center gap-2">
              <span className={c.ok ? "text-emerald-600" : "text-rose-600"}>{c.ok ? "✓" : "✗"}</span>
              <span className="text-slate-700">{c.name}</span>
              <span className="font-mono text-xs text-slate-400">{c.expr}</span>
            </div>
          ))}
          {(step.warnings ?? []).map((w, i) => (
            <div key={`w${i}`} className="text-sm rounded bg-amber-50 border border-amber-200 px-2 py-1 text-amber-800">
              ⓘ {w.message} <span className="text-xs">({w.sentence})</span>
            </div>
          ))}
          {step.checks.length === 0 && !(step.warnings ?? []).length && <p className="text-sm text-slate-400">검사 없음</p>}
        </div>
      )}
      {step.stage === "symptom_free" && (
        step.exhibited.length === 0
          ? <p className="text-sm text-emerald-600">유발 증상 없음</p>
          : <ul className="space-y-1">
              {step.exhibited.map((s, i) => (
                <li key={i} className="text-sm">
                  <Chip color="rose">{s.label}</Chip>
                  <span className="ml-2 text-xs text-slate-500">근거 {s.sentences.join(" · ")}</span>
                </li>
              ))}
            </ul>
      )}
    </div>
  );
}

function SatisfyResult({ r }: { r: SatisfyResponse }) {
  const orderedSteps = STAGE_ORDER.map((s) => r.steps.find((x) => x.stage === s)).filter(Boolean) as Step[];
  return (
    <div className="space-y-4">
      <Verdict r={r} />

      {r.applied_categories && (
        <p className="text-xs text-slate-500">적용 지식범위: {r.applied_categories.map((c) => <Chip key={c}>{c}</Chip>)}</p>
      )}

      <Card title="검증 3단계 (순서 고정)">
        <div className="space-y-2">
          {orderedSteps.map((s) => <StepView key={s.stage} step={s} />)}
        </div>
      </Card>

      {r.violated_requirements.length > 0 && (
        <Card title="위반 요구 (violated_requirements)" tone="bad">
          <ul className="space-y-2">
            {r.violated_requirements.map((vr) => (
              <li key={vr.rb} className="text-sm">
                <Chip color="rose">{vr.rb}</Chip>
                <span className="ml-2 font-medium">{vr.label}</span>
                <span className="ml-2 text-slate-500">금지 증상 {vr.forbids} · 근거 {vr.sentences.join(" · ")}</span>
              </li>
            ))}
          </ul>
          {r.violations.length > 0 && (
            <p className="mt-3 text-xs text-slate-500">위반 문장(정규화): {r.violations.map((v) => <Chip key={v} color="rose">{v}</Chip>)}</p>
          )}
        </Card>
      )}

      {r.alternatives.length > 0 && (
        <Card title="허용 대안 (alternatives)" tone="ok">
          <ul className="flex flex-wrap gap-2">
            {r.alternatives.map((a, i) => <li key={i}><Chip color="emerald">{a}</Chip></li>)}
          </ul>
        </Card>
      )}

      {r.justification && r.justification.length > 0 && (
        <Card title="근거 (justification)">
          <ol className="space-y-1 text-sm text-slate-600 list-decimal list-inside">
            {r.justification.map((j, i) => <li key={i}>{j}</li>)}
          </ol>
        </Card>
      )}
    </div>
  );
}
