/** SC-1P 프로젝트 요구사항 (FR-3b, AC-1P) — 프로젝트 생성 → 자연어 RB 파싱, 미지 증상 유도. */
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiCallError } from "../api/client";
import { Button, Card, Chip, ErrorNotice, Spinner } from "../components/ui";
import { useApp } from "../store";
import type { RequirementsResponse } from "../types/contracts";

const SAMPLE = "겨울철에도 소음이 없고 중형 SUV에서 떨림이 없어야 한다";
const SAMPLE_UNKNOWN = "겨울철에 소음이 없고 유막이 남지 않아야 한다";
const ALL_CATEGORIES = ["소음", "떨림"];

export default function Requirements() {
  const { project, setProject, setProjectRequirements } = useApp();

  // 프로젝트 생성 폼
  const [name, setName] = useState("겨울용 SUV 와이퍼");
  const [vehicle, setVehicle] = useState("MidSizeSUV");
  const [env, setEnv] = useState("Winter");
  const [categories, setCategories] = useState<string[]>(["떨림"]);
  const [creating, setCreating] = useState(false);
  const [createErr, setCreateErr] = useState<string | null>(null);

  // 요구 파싱
  const [text, setText] = useState(SAMPLE);
  const [result, setResult] = useState<RequirementsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleCat = (c: string) => setCategories((p) => p.includes(c) ? p.filter((x) => x !== c) : [...p, c]);

  async function createProject() {
    setCreating(true); setCreateErr(null); setResult(null);
    try {
      const p = await api.createProject({ name, target_vehicle: vehicle, target_env: env, knowledge_categories: categories });
      setProject({ id: p.id, name: p.name, categories: p.knowledge_categories ?? categories, requirements: [] });
    } catch (e) {
      setCreateErr(e instanceof ApiCallError ? e.body.user_message : "프로젝트 생성에 실패했습니다.");
    } finally {
      setCreating(false);
    }
  }

  async function parse() {
    if (!project) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await api.parseRequirements(project.id, { text });
      setResult(r);
      setProjectRequirements(r.requirements);
    } catch (e) {
      setError(e instanceof ApiCallError ? e.body.user_message : "요구 파싱에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold">프로젝트 요구사항</h1>
        <p className="text-sm text-slate-500 mt-1">요구는 이 프로젝트에만 적용됩니다(도메인 지식과 별개). 설계 검증(satisfy)은 먼저 프로젝트가 있어야 동작합니다.</p>
      </div>

      {/* 1. 프로젝트 생성/선택 */}
      <Card title="1. 프로젝트" tone={project ? "ok" : "plain"}>
        {project ? (
          <div className="space-y-2 text-sm">
            <p>현재 프로젝트: <span className="font-medium">{project.name}</span> <Chip color="blue">{project.id}</Chip></p>
            <p>지식범위: {project.categories.map((c) => <Chip key={c} color="violet">{c}</Chip>)}</p>
            <Button variant="ghost" onClick={() => { setProject(null); setResult(null); }}>새 프로젝트 만들기</Button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
              <label className="flex flex-col gap-1"><span className="text-xs text-slate-500">이름</span>
                <input value={name} onChange={(e) => setName(e.target.value)} className="rounded border border-slate-300 px-2 py-1.5" /></label>
              <label className="flex flex-col gap-1"><span className="text-xs text-slate-500">차종</span>
                <select value={vehicle} onChange={(e) => setVehicle(e.target.value)} className="rounded border border-slate-300 px-2 py-1.5">
                  <option value="MidSizeSUV">중형 SUV</option><option value="CompactSedan">소형 세단</option></select></label>
              <label className="flex flex-col gap-1"><span className="text-xs text-slate-500">환경</span>
                <select value={env} onChange={(e) => setEnv(e.target.value)} className="rounded border border-slate-300 px-2 py-1.5">
                  <option value="Winter">Winter</option></select></label>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-1">적용 지식 카테고리 (CD-4 — satisfy 게이트 컴파일 범위)</p>
              <div className="flex gap-4 text-sm">
                {ALL_CATEGORIES.map((c) => (
                  <label key={c} className="flex items-center gap-1.5">
                    <input type="checkbox" checked={categories.includes(c)} onChange={() => toggleCat(c)} /> {c}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button onClick={createProject} disabled={creating || !name.trim() || categories.length === 0}>
                {creating ? "생성 중…" : "프로젝트 생성"}
              </Button>
              {creating && <Spinner />}
            </div>
            {createErr && <ErrorNotice message={createErr} actionLabel="다시 시도" onAction={createProject} />}
          </div>
        )}
      </Card>

      {/* 2. 요구 파싱 */}
      <Card title="2. 자연어 요구 → RequiredBehavior">
        {!project ? (
          <p className="text-sm text-slate-400">먼저 프로젝트를 생성하세요.</p>
        ) : (
          <>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
              className="w-full rounded-md border border-slate-300 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400" />
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              <Button onClick={parse} disabled={loading || !text.trim()}>{loading ? "파싱 중…" : "요구 파싱"}</Button>
              <Button variant="ghost" onClick={() => setText(SAMPLE)}>정상 예시</Button>
              <Button variant="ghost" onClick={() => setText(SAMPLE_UNKNOWN)}>미지 증상 예시</Button>
              {loading && <Spinner />}
            </div>
          </>
        )}
      </Card>

      {error && <ErrorNotice message={error} actionLabel="다시 시도" onAction={parse} />}

      {result && (
        <>
          <Card title="파싱된 요구 (RequiredBehavior)" tone="ok">
            {result.requirements.length === 0 ? (
              <p className="text-sm text-slate-500">파싱된 요구가 없습니다.</p>
            ) : (
              <ul className="space-y-2">
                {result.requirements.map((r) => (
                  <li key={r.id} className="text-sm flex items-center gap-2">
                    <Chip color="amber">{r.id}</Chip>
                    <span className="font-medium">{r.label}</span>
                    <span className="text-xs text-slate-500 font-mono">¬∃exhibits.{r.forbids_symptom}</span>
                  </li>
                ))}
              </ul>
            )}
            {result.requirements.length > 0 && (
              <p className="mt-3 text-sm"><Link to="/verify" className="text-blue-600 underline">→ 설계 검증으로 이동</Link></p>
            )}
          </Card>

          {result.unknown_symptoms.length > 0 && (
            <Card title="미지 증상 — 지식 추가 필요 (AC-1P)" tone="warn">
              <p className="text-sm text-amber-800">
                다음 증상은 도메인 지식(M1)에 없어 요구로 저장되지 않았습니다:
                {result.unknown_symptoms.map((s) => <Chip key={s} color="amber">{s}</Chip>)}
              </p>
              <p className="mt-2 text-sm">
                <Link to="/input" className="text-blue-600 underline">지식 입력 화면에서 이 증상을 추가하세요 →</Link>
              </p>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
