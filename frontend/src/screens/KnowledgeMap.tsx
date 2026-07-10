/** T-61 지식맵 (FR-10, AC-4) — Cytoscape. inferred=true 엣지는 점선. 노드 클릭 → 출처 추적. */
import cytoscape from "cytoscape";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import { Card, Chip, ErrorNotice, Spinner } from "../components/ui";
import type { GraphResponse, GraphNode } from "../types/contracts";

const KIND_COLOR: Record<string, string> = {
  sentence: "#3b82f6", rule: "#8b5cf6", symptom: "#ef4444",
  concept: "#64748b", design: "#0ea5e9", requirement: "#f59e0b", class: "#334155",
};

export default function KnowledgeMap() {
  const [data, setData] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [layer, setLayer] = useState<string>("");
  const [symptom, setSymptom] = useState<string>("");
  const [sentence, setSentence] = useState<string>("");
  const boxRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  async function load() {
    setLoading(true); setError(null);
    const params: Record<string, string> = {};
    if (layer) params.layer = layer;
    if (symptom) params.symptom = symptom;
    if (sentence) params.sentence = sentence;
    try {
      setData(await api.graph(params));
    } catch {
      setError("지식맵을 불러오지 못했습니다. 다시 시도해 주세요.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  // 클라이언트 필터 (mock 은 단일 fixture 반환 → 화면에서 필터 적용)
  const filtered = useMemo(() => {
    if (!data) return null;
    let nodes = data.nodes;
    if (layer) nodes = nodes.filter((n) => n.layer === layer);
    if (sentence) nodes = nodes.filter((n) => n.kind !== "sentence" || n.id === sentence || n.id.split(",").includes(sentence));
    const ids = new Set(nodes.map((n) => n.id));
    const edges = data.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return { nodes, edges };
  }, [data, layer, sentence]);

  useEffect(() => {
    if (!boxRef.current || !filtered) return;
    const cy = cytoscape({
      container: boxRef.current,
      elements: [
        ...filtered.nodes.map((n) => ({ data: { id: n.id, label: n.label, kind: n.kind, color: KIND_COLOR[n.kind] ?? "#64748b", inferred: n.inferred ? "1" : "0" } })),
        ...filtered.edges.map((e, i) => ({ data: { id: `e${i}`, source: e.source, target: e.target, label: e.predicate, inferred: e.inferred ? "1" : "0" } })),
      ],
      style: [
        { selector: "node", style: {
          "background-color": "data(color)",
          label: "data(label)", color: "#0f172a", "font-size": 10, "text-wrap": "wrap", "text-max-width": "90px",
          "text-valign": "bottom", "text-margin-y": 3, width: 26, height: 26,
        } },
        { selector: 'node[inferred="1"]', style: { "border-width": 2, "border-style": "dashed", "border-color": "#94a3b8" } },
        { selector: "edge", style: {
          width: 1.5, "line-color": "#cbd5e1", "target-arrow-color": "#cbd5e1", "target-arrow-shape": "triangle",
          "curve-style": "bezier", label: "data(label)", "font-size": 8, color: "#94a3b8",
        } },
        // AC-4 핵심: inferred 엣지는 점선
        { selector: 'edge[inferred="1"]', style: { "line-style": "dashed", "line-color": "#a78bfa", "target-arrow-color": "#a78bfa", width: 2 } },
        { selector: "node:selected", style: { "border-width": 3, "border-color": "#0f172a", "border-style": "solid" } },
      ],
      layout: { name: "cose", animate: false, padding: 30 },
    });
    cy.on("tap", "node", (evt) => {
      const id = evt.target.id();
      setSelected(data?.nodes.find((n) => n.id === id) ?? null);
    });
    cy.on("tap", (evt) => { if (evt.target === cy) setSelected(null); });
    cyRef.current = cy;
    return () => cy.destroy();
  }, [filtered, data]);

  // 선택 노드의 출처 추적: 연결된 엣지에서 evidence(문장)·규칙 수집
  const trace = useMemo(() => {
    if (!selected || !data) return null;
    const sentences = new Set<string>();
    const rules = new Set<string>();
    for (const e of data.edges) {
      if (e.source === selected.id || e.target === selected.id) {
        if (e.evidence) e.evidence.split(",").forEach((s) => sentences.add(s.trim()));
        const other = data.nodes.find((n) => n.id === (e.source === selected.id ? e.target : e.source));
        if (other?.kind === "rule") rules.add(other.id);
      }
    }
    if (selected.kind === "rule") rules.add(selected.id);
    if (selected.kind === "sentence") sentences.add(selected.id);
    return { sentences: [...sentences], rules: [...rules] };
  }, [selected, data]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold">지식맵</h1>
        <p className="text-sm text-slate-500 mt-1">추론(inferred) 관계는 점선입니다. 노드를 클릭하면 근거 문장·규칙·IRI 를 추적합니다.</p>
      </div>

      <Card>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1"><span className="text-xs text-slate-500">층 (layer)</span>
            <select value={layer} onChange={(e) => setLayer(e.target.value)} className="rounded border border-slate-300 px-2 py-1">
              <option value="">전체</option><option value="M0">M0</option><option value="M1">M1</option><option value="M2">M2</option>
            </select>
          </label>
          <label className="flex flex-col gap-1"><span className="text-xs text-slate-500">증상 (symptom)</span>
            <input value={symptom} onChange={(e) => setSymptom(e.target.value)} placeholder="TipChatter" className="rounded border border-slate-300 px-2 py-1" />
          </label>
          <label className="flex flex-col gap-1"><span className="text-xs text-slate-500">문장 (sentence)</span>
            <input value={sentence} onChange={(e) => setSentence(e.target.value)} placeholder="S3" className="rounded border border-slate-300 px-2 py-1" />
          </label>
          <button onClick={load} className="rounded-md bg-slate-900 px-3 py-1.5 text-white text-sm">서버 조회</button>
          {loading && <Spinner label="로딩…" />}
          {(layer || symptom || sentence) && (
            <button onClick={() => { setLayer(""); setSymptom(""); setSentence(""); }} className="text-xs text-slate-500 underline">필터 초기화</button>
          )}
        </div>
        {data && (
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
            <span>노드 {data.stats.nodes}</span><span>엣지 {data.stats.edges}</span>
            <span className="text-violet-600">추론 엣지 {data.stats.inferred_edges ?? 0} (점선)</span>
          </div>
        )}
      </Card>

      {error && <ErrorNotice message={error} actionLabel="다시 시도" onAction={load} />}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2">
          <Card>
            <div ref={boxRef} className="cy-canvas rounded-md bg-slate-50 border border-slate-100" />
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              {Object.entries(KIND_COLOR).map(([k, c]) => (
                <span key={k} className="inline-flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: c }} />{k}</span>
              ))}
              <span className="inline-flex items-center gap-1 text-violet-600">┈┈ 추론(inferred)</span>
            </div>
          </Card>
        </div>

        <Card title="출처 추적">
          {!selected ? (
            <p className="text-sm text-slate-400">노드를 클릭하면 근거를 표시합니다.</p>
          ) : (
            <div className="space-y-3 text-sm">
              <div>
                <Chip color="slate">{selected.kind}</Chip> <span className="font-medium ml-1">{selected.label}</span>
              </div>
              {selected.text && <p className="text-slate-700 bg-slate-50 rounded p-2 border border-slate-100">{selected.text}</p>}
              <div>
                <p className="text-xs text-slate-500">IRI</p>
                <p className="font-mono text-xs text-slate-600 break-all">{selected.iri}</p>
              </div>
              {trace && trace.sentences.length > 0 && (
                <div><p className="text-xs text-slate-500 mb-1">근거 문장</p><div className="flex flex-wrap gap-1.5">{trace.sentences.map((s) => <Chip key={s} color="blue">{s}</Chip>)}</div></div>
              )}
              {trace && trace.rules.length > 0 && (
                <div><p className="text-xs text-slate-500 mb-1">관련 규칙</p><div className="flex flex-wrap gap-1.5">{trace.rules.map((r) => <Chip key={r} color="violet">{r}</Chip>)}</div></div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
