#!/usr/bin/env python3
"""T-70 — 회귀셋 실 스택 러너 (게이트).

BFF 외부 표면(`/api/v1`)만 두드린다. **실키·실스택으로 판정한다** — mock 통과는 무의미하다.
knowledge(:8000)·bff(:4000)가 실키 모드로 떠 있어야 한다(ANTHROPIC_API_KEY 설정, AI_MOCK_MODE 미설정).

각 항목은 `kind` 로 디스패치한다. 통과/실패/스킵을 항목별로 보고하고,
**하나라도 FAIL 이면 exit 1**(CI 게이트). SKIP 은 이유를 반드시 남긴다(무언의 누락 금지).

사용:
  python run_regression.py --bff http://localhost:4000
  python run_regression.py --only guard-tire-pressure,sat-bad
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
DEFAULT_SET = HERE.parent / "contracts" / "mocks" / "regression_set.jsonl"


class Result:
    def __init__(self, rid: str, status: str, detail: str) -> None:
        self.id = rid
        self.status = status  # PASS · FAIL · SKIP
        self.detail = detail


def _need(cond: bool, msg: str) -> str | None:
    return None if cond else msg


def _parse_sse(text: str) -> list[tuple[str, Any]]:
    """SSE 본문 → [(event, data_json)] (data 는 JSON 파싱, 실패 시 원문)."""
    out: list[tuple[str, Any]] = []
    event = "message"
    for block in text.split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        data_parts = []
        ev = event
        for ln in lines:
            if ln.startswith("event:"):
                ev = ln[len("event:"):].strip()
            elif ln.startswith("data:"):
                data_parts.append(ln[len("data:"):].strip())
        if data_parts:
            raw = "\n".join(data_parts)
            try:
                out.append((ev, json.loads(raw)))
            except json.JSONDecodeError:
                out.append((ev, raw))
    return out


# ── kind 별 디스패치 ─────────────────────────────────────────────────────────
def run_satisfy(c: httpx.Client, bff: str, e: dict) -> str | None:
    i, exp = e["input"], e["expected"]
    r = c.post(f"{bff}/api/v1/satisfy", json={
        "project_id": i.get("project_id", "regression"),
        "design": i["design"], "require": i.get("require", []), "categories": i.get("categories"),
    })
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    b = r.json()
    errs = []
    if "satisfies" in exp:
        errs.append(_need(b.get("satisfies") == exp["satisfies"], f"satisfies={b.get('satisfies')} 기대 {exp['satisfies']}"))
    if "violations" in exp:
        errs.append(_need(b.get("violations") == exp["violations"], f"violations={b.get('violations')} 기대 {exp['violations']}"))
    if "pending_reason" in exp:
        errs.append(_need(b.get("pending_reason") == exp["pending_reason"], f"pending_reason={b.get('pending_reason')}"))
    return "; ".join(x for x in errs if x) or None


def run_qa(c: httpx.Client, bff: str, e: dict) -> str | None:
    i, exp = e["input"], e["expected"]
    r = c.post(f"{bff}/api/v1/qa", json={"question": i["question"], "mode": i.get("mode", "verified")})
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    b = r.json()
    va = b.get("verified_answer") or {}
    sources = va.get("sources") or []
    errs = []
    if "layer" in exp:
        errs.append(_need(b.get("layer") == exp["layer"], f"layer={b.get('layer')} 기대 {exp['layer']}"))
    if "insufficient_evidence" in exp:
        errs.append(_need(b.get("insufficient_evidence") == exp["insufficient_evidence"],
                          f"insufficient_evidence={b.get('insufficient_evidence')} 기대 {exp['insufficient_evidence']}"))
    if exp.get("sources_empty"):
        errs.append(_need(sources == [], f"sources 비어야 하는데 {len(sources)}건"))
    if exp.get("sources_nonempty"):
        errs.append(_need(len(sources) > 0, "sources 가 비었다(근거 있어야 함)"))
    if "answer_contains" in exp:
        errs.append(_need(exp["answer_contains"] in (va.get("text") or ""), f"answer 에 '{exp['answer_contains']}' 없음"))
    if "determinism" in exp:
        errs.append(_need(va.get("determinism") == exp["determinism"], f"determinism={va.get('determinism')}"))
    if exp.get("llm_answer_present"):
        errs.append(_need(b.get("llm_answer") is not None, "llm_answer 가 없다(환각비교 미동작)"))
    return "; ".join(x for x in errs if x) or None


def run_extraction_validate(c: httpx.Client, bff: str, e: dict) -> str | None:
    """두 모드:
    - input.concepts/relations 명시 → /extraction/validate 직접(결정론 SHACL 게이트 검증).
    - input.text → /extraction/stream(SSE, 실 LLM 추출) → validation 이벤트.
    LLM 추출은 변동적이므로 개념은 부분일치(substring)로만 단언한다(안정 속성).
    """
    i, exp = e["input"], e["expected"]
    if "concepts" in i or "relations" in i:
        r = c.post(f"{bff}/api/v1/extraction/validate",
                   json={"concepts": i.get("concepts", []), "relations": i.get("relations", [])})
        if r.status_code != 200:
            return f"HTTP {r.status_code}: {r.text[:200]}"
        validation = r.json()
        concepts = [ct.get("label") for ct in i.get("concepts", [])]
    else:
        r = c.post(f"{bff}/api/v1/extraction/stream", json={"text": i["text"]},
                   headers={"Accept": "text/event-stream"})
        if r.status_code != 200:
            return f"HTTP {r.status_code}: {r.text[:200]}"
        events = _parse_sse(r.text)
        concepts = [d.get("label") for ev, d in events if ev == "concept" and isinstance(d, dict)]
        validation = next((d for ev, d in events if ev == "validation" and isinstance(d, dict)), None)
        if validation is None:
            return "validation 이벤트 없음"
    errs = []
    if "conforms" in exp:
        errs.append(_need(validation.get("conforms") == exp["conforms"], f"conforms={validation.get('conforms')} 기대 {exp['conforms']}"))
    if "offender" in exp:
        offenders = [v.get("offender") for v in validation.get("violations", []) if isinstance(v, dict)]
        errs.append(_need(exp["offender"] in offenders, f"offender '{exp['offender']}' 없음 (있는 것: {offenders})"))
    for label in exp.get("concepts_include", []):
        errs.append(_need(any(label in (cc or "") for cc in concepts), f"개념 '{label}' 미추출 (추출: {concepts})"))
    return "; ".join(x for x in errs if x) or None


def run_graph(c: httpx.Client, bff: str, e: dict) -> str | None:
    i, exp = e["input"], e["expected"]
    r = c.get(f"{bff}/api/v1/graph", params={k: v for k, v in i.items()})
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    b = r.json()
    ids = {n["id"] for n in b.get("nodes", [])}
    errs = []
    for nid in exp.get("nodes_include", []):
        errs.append(_need(nid in ids, f"노드 '{nid}' 없음"))
    if exp.get("has_inferred_edge"):
        errs.append(_need(b.get("stats", {}).get("inferred_edges", 0) > 0, "inferred 엣지가 0 (점선 미렌더)"))
    return "; ".join(x for x in errs if x) or None


def run_governance(c: httpx.Client, bff: str, e: dict) -> str | None:
    i, exp = e["input"], e["expected"]
    role = i.get("role", "admin")
    r = c.request("DELETE", f"{bff}/api/v1/governance/concepts/{i['delete']}",
                  headers={"X-Role": role})
    errs = [_need(r.status_code == exp["http"], f"HTTP {r.status_code} 기대 {exp['http']}")]
    if "code" in exp:
        code = (r.json() or {}).get("code")
        errs.append(_need(code == exp["code"], f"code={code} 기대 {exp['code']}"))
    return "; ".join(x for x in errs if x) or None


def run_rules_dryrun(c: httpx.Client, bff: str, e: dict) -> str | None:
    i, exp = e["input"], e["expected"]
    r = c.post(f"{bff}/api/v1/rules/dry-run",
               json={"override_ttl": i["override_ttl"], "categories": i.get("categories")},
               headers={"X-Role": i.get("role", "admin")})
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}"
    b = r.json()
    nv = b.get("new_violations") or []
    nv_count = len(nv) if isinstance(nv, list) else (nv if isinstance(nv, int) else 0)
    affected = [a.get("id") if isinstance(a, dict) else str(a) for a in (b.get("affected_instances") or [])]
    errs = [_need(nv_count >= exp.get("new_violations_min", 0), f"new_violations={nv_count} < {exp.get('new_violations_min')}")]
    for inst in exp.get("affected_instances_include", []):
        errs.append(_need(any(inst in a for a in affected), f"영향 인스턴스 '{inst}' 없음 (있는 것: {affected})"))
    return "; ".join(x for x in errs if x) or None


def run_extraction_save(c: httpx.Client, bff: str, e: dict) -> str | None:
    i, exp = e["input"], e["expected"]
    r = c.post(f"{bff}/api/v1/extraction/save", json={**i, "draft_id": f"reg-{e['id']}"})
    if r.status_code not in (200, 201):
        return f"HTTP {r.status_code}: {r.text[:200]}"
    b = r.json()
    errs = []
    if exp.get("derived_rule_present"):
        derived = b.get("derived") or {}
        errs.append(_need(bool(derived.get("rule")), "derived.rule 없음"))
    if "human_view_contains" in exp:
        hv = json.dumps(b.get("human_view"), ensure_ascii=False)
        errs.append(_need(exp["human_view_contains"] in hv, f"human_view 에 '{exp['human_view_contains']}' 없음"))
    return "; ".join(x for x in errs if x) or None


DISPATCH = {
    "satisfy": run_satisfy,
    "qa": run_qa,
    "qa_guardrail": run_qa,
    "extraction_validate": run_extraction_validate,
    "extraction_save": run_extraction_save,
    "graph": run_graph,
    "governance": run_governance,
    "rules_dryrun": run_rules_dryrun,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="회귀셋 실 스택 러너 (T-70)")
    ap.add_argument("--bff", default="http://localhost:4000", help="BFF base URL")
    ap.add_argument("--set", default=str(DEFAULT_SET), help="regression_set.jsonl 경로")
    ap.add_argument("--only", default="", help="쉼표구분 id 필터")
    ap.add_argument("--timeout", type=float, default=90.0)
    args = ap.parse_args()

    try:  # 윈도우 cp949 콘솔에서도 한글 detail 이 깨지거나 죽지 않게
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    only = {x for x in args.only.split(",") if x}
    entries = [json.loads(ln) for ln in Path(args.set).read_text(encoding="utf-8").splitlines() if ln.strip()]
    if only:
        entries = [e for e in entries if e["id"] in only]

    results: list[Result] = []
    with httpx.Client(timeout=args.timeout) as c:
        for e in entries:
            rid, kind = e["id"], e.get("kind", "")
            if kind == "meta":
                results.append(Result(rid, "SKIP", "meta — 실키 러너 범위 밖(mock 모드 CI 잡)"))
                continue
            fn = DISPATCH.get(kind)
            if fn is None:
                results.append(Result(rid, "SKIP", f"미지원 kind={kind}"))
                continue
            try:
                detail = fn(c, args.bff, e)
            except Exception as exc:  # noqa: BLE001 — 러너는 항목 실패를 삼키지 않고 보고한다
                results.append(Result(rid, "FAIL", f"예외: {type(exc).__name__}: {exc}"))
                continue
            results.append(Result(rid, "PASS" if detail is None else "FAIL", detail or "ok"))

    # ── 보고 ──
    npass = sum(1 for r in results if r.status == "PASS")
    nfail = sum(1 for r in results if r.status == "FAIL")
    nskip = sum(1 for r in results if r.status == "SKIP")
    print(f"\n=== 회귀 실 스택 결과 (BFF {args.bff}) ===")
    for r in results:
        mark = {"PASS": "[OK]", "FAIL": "[XX]", "SKIP": "[--]"}[r.status]
        line = f"{mark} {r.id:26s} [{r.status}]"
        if r.status != "PASS":
            line += f"  {r.detail}"
        print(line)
    print(f"\n합계: PASS {npass} · FAIL {nfail} · SKIP {nskip} / 총 {len(results)}")
    if nskip:
        print("(SKIP 은 이유를 명시했다 — 무언의 누락 아님)")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
