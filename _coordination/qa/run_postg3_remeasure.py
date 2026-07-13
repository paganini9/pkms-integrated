"""③′ 소형 재측정 — 1단계(T-92·T-94·T-93) 후 저작 루프 회복 관측.

게이트 아님. 결함은 로그만 남긴다(수정 금지).
실행: python remeasure.py <step>   step: ab | author | flagship | rb | invariant | all
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BFF = "http://localhost:4000/api/v1"
KB = "http://localhost:8000"
OUT = Path(__file__).parent / "results-remeasure"
OUT.mkdir(exist_ok=True)

K = {
    "K1": "고속 주행 시 스포일러 없는 블레이드는 들뜸이 발생한다.",
    "K2": "오존 노출이 기준을 초과하면 고무 블레이드에 균열이 생긴다.",
    "K3": "영하 40도에서 고무가 경화되어 와이퍼 작동 불량이 발생한다.",
    "K4": "염화칼슘에 반복 노출되면 블레이드 프레임에 부식이 발생한다.",
    "K5": "블레이드 길이가 커넥터 규격과 맞지 않으면 주행 중 이탈이 발생한다.",
}
R = {
    "R1": "블레이드는 고속 주행 중 들뜸 현상이 발생하지 않아야 한다.",
    "R5": "블레이드 고무 재질은 기준치 이상의 오존 및 자외선 노출 환경에서 균열이나 경화가 발생하지 않아야 한다.",
}

#: 각 K 문장이 필요로 하는 신규 개념(거버넌스 승인 대상) — 증상/환경조건.
#: 한글 표면어는 altLabel 로 부착한다(T-89 어휘층). 부품/속성류는 편입하지 않는다(범위 최소).
GOVERNANCE = {
    "K1": [("Lift", "Symptom", ["들뜸", "들뜸 현상"]), ("HighSpeed", "EnvCondition", ["고속 주행", "고속 주행 중", "주행 중"])],
    "K2": [("Ozone", "EnvCondition", ["오존", "오존 노출"]), ("Crack", "Symptom", ["균열"])],
    "K3": [("SubZero40", "EnvCondition", ["영하 40도", "영하 40도 환경"]), ("Malfunction", "Symptom", ["작동 불량"]),
           ("Hardening", "Symptom", ["경화"])],
    "K4": [("CalciumChloride", "EnvCondition", ["염화칼슘", "염화칼슘 노출", "반복 노출"]), ("Corrosion", "Symptom", ["부식"])],
    "K5": [("Detachment", "Symptom", ["이탈", "주행 중 이탈"]), ("Driving", "EnvCondition", ["주행", "주행 중"])],
}

SAT_BAD = {"material": "Rubber", "length_mm": 600, "spring_n": 8, "arm_shape": "simple",
           "vehicle": "MidSizeSUV", "env": "Winter"}
SAT_GOOD = {"material": "Silicone", "length_mm": 550, "spring_n": 12, "arm_shape": "complex",
            "vehicle": "CompactSedan", "env": "Winter"}


def call(url, body=None, method=None, admin=False, timeout=240):  # noqa: ANN001, ANN201
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    req.add_header("Content-Type", "application/json")
    if admin:
        req.add_header("X-Role", "admin")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"status": r.status, "body": json.loads(r.read() or b"{}"), "ms": int((time.time() - t0) * 1000)}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            b = json.loads(raw or b"{}")
        except Exception:  # noqa: BLE001
            b = {"raw": raw.decode(errors="replace")[:400]}
        return {"status": e.code, "body": b, "ms": int((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        return {"status": 0, "body": {"error": repr(e)}, "ms": int((time.time() - t0) * 1000)}


def dump(name, obj):  # noqa: ANN001, ANN201
    (OUT / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → results-remeasure/{name}.json")


def project() -> str:
    r = call(f"{BFF}/projects", {"name": "postg3-재측정", "target_vehicle": "MidSizeSUV",
                                 "target_env": "Winter", "knowledge_categories": ["소음", "떨림"]})
    return r["body"]["id"]


def causation_rows() -> list:
    q = call(f"{KB}/sparql", {"query":
        "SELECT ?c ?m ?cond ?s WHERE { ?c a <http://ex.org/spmm-ext#Causation> ; "
        "<http://ex.org/spmm-ext#hasMechanism> ?m ; <http://ex.org/spmm-ext#manifestsSymptom> ?s . "
        "OPTIONAL { ?c <http://ex.org/spmm-ext#underCondition> ?cond } }"})
    return q["body"].get("rows", [])


def rules() -> list:
    return [r["id"] for r in call(f"{KB}/rules")["body"]["rules"]]


def approve(sid: str) -> list:
    """거버넌스: 그 문장이 쓰는 신규 개념 편입(클래스 add → 한글 altLabel 승인)."""
    log = []
    changes = [{"op": "add", "id": cid, "parent": parent} for cid, parent, _ in GOVERNANCE[sid]]
    g = call(f"{BFF}/upper-ontology/classes", {"approved": True, "changes": changes}, admin=True)
    log.append({"add": changes, "status": g["status"], "body": g["body"]})
    for cid, _parent, labels in GOVERNANCE[sid]:
        for lb in labels:
            a = call(f"{KB}/oov/approve", {"concept_iri": f"http://ex.org/spmm-ext#{cid}",
                                           "label": lb, "approved": True})
            log.append({"altLabel": lb, "concept": cid, "status": a["status"]})
    return log


# ── (3) A/B — K1~K5 를 Claude vs Solar 로 추출 ───────────────────────────────
def step_ab(pid: str) -> dict:
    out = {}
    for sid, text in K.items():
        print(f"[ab] {sid}")
        ab = call(f"{BFF}/extraction/ab", {"text": text, "providers": ["claude", "solar"]})
        rec = {"text": text, "results": {}}
        for res in ab["body"].get("results", []):
            p = res["requested_provider"]
            entry = {"concepts": res.get("concepts", []), "relations": res.get("relations", []),
                     "actual": res.get("actual_provider"), "error": res.get("error")}
            v = call(f"{BFF}/extraction/validate", {"concepts": entry["concepts"],
                                                    "relations": entry["relations"], "project_id": pid})
            entry["validate"] = v["body"]
            rec["results"][p] = entry
        out[sid] = rec
        dump("ab", out)
    return out


# ── (1) K1~K5 저작 엔드투엔드 (저작 provider = claude, 정책 기본) ─────────────
def step_author(pid: str, ab: dict | None = None) -> dict:
    ab = ab or json.loads((OUT / "ab.json").read_text(encoding="utf-8"))
    out = {}
    for sid, text in K.items():
        print(f"[author] {sid}")
        rec: dict = {"text": text}
        claude = ab[sid]["results"]["claude"]
        concepts, relations = claude["concepts"], claude["relations"]
        rec["extract"] = {"concepts": concepts, "relations": relations}

        # (a) 승인 전 검증 — OOV·타입 상태
        rec["validate_before"] = call(f"{BFF}/extraction/validate", {
            "concepts": concepts, "relations": relations, "project_id": pid})["body"]

        # (b) 거버넌스 승인 편입(신규 개념 + 한글 altLabel)
        rec["governance"] = approve(sid)

        # (c) 승인 후 재검증
        rec["validate_after"] = call(f"{BFF}/extraction/validate", {
            "concepts": concepts, "relations": relations, "project_id": pid})["body"]

        # (d) satisfy 전 상태
        before_rules = rules()
        before_caus = len(causation_rows())

        # (e) 저장(HITL 승인)
        s = call(f"{BFF}/extraction/save", {
            "sentence_text": text, "concepts": concepts, "relations": relations,
            "category": "소음", "approved": True, "draft_id": f"remeasure-{sid}", "project_id": pid})
        rec["save"] = {"status": s["status"], "body": s["body"]}
        print(f"   save={s['status']}", end="")
        if s["status"] == 201:
            d = s["body"]["derived"]["rule"]
            rec["derived"] = {"id": d["id"], "about_symptom": d["about_symptom"],
                              "polarity": d["polarity"],
                              "conds": [(c["path"], c["val"]) for c in d["conds"]]}
            rec["mentions"] = s["body"]["sentence"]["mentions"]
            print(f" rule={d['id']} sym={d['about_symptom']} conds={rec['derived']['conds']}", end="")
        rec["rules_before"], rec["rules_after"] = before_rules, rules()
        rec["causation_before"], rec["causation_after"] = before_caus, len(causation_rows())
        print(f" causation {before_caus}→{rec['causation_after']}")
        out[sid] = rec
        dump("author", out)
    out["_final"] = {"rules": rules(), "causation": causation_rows()}
    dump("author", out)
    return out


# ── (2) K2 플래그십 실스택 루프 (satisfy 판정 변화) ──────────────────────────
def step_flagship(pid: str) -> dict:
    out = {}
    design = {"id": "D-ozone", "material": "Rubber", "vehicle": "MidSizeSUV",
              "length_mm": 550, "spring_n": 12, "arm_shape": "complex", "env": "Ozone"}
    out["design"] = design
    out["satisfy_ozone"] = call(f"{BFF}/satisfy", {"project_id": pid, "design": design})["body"]
    ex = [(e["symptom"], e["sentences"]) for e in out["satisfy_ozone"]["steps"][2]["exhibited"]]
    print(f"  env=Ozone 설계: satisfies={out['satisfy_ozone']['satisfies']} exhibited={ex}")

    # 각 K 문장의 환경조건별 설계 — 저작 지식이 판정에 닿는지
    for sid, envv in (("K1", "HighSpeed"), ("K3", "SubZero40"), ("K4", "CalciumChloride"), ("K5", "Driving")):
        d = {**design, "id": f"D-{envv}", "env": envv}
        r = call(f"{BFF}/satisfy", {"project_id": pid, "design": d})["body"]
        e = [(x["symptom"], x["sentences"]) for x in r["steps"][2]["exhibited"]]
        out[f"satisfy_{envv}"] = r
        print(f"  env={envv:16} satisfies={r['satisfies']} exhibited={e}")
    dump("flagship", out)
    return out


# ── (4) R1·R5 → M2/RB 경로 ─────────────────────────────────────────────────
def step_rb(pid: str) -> dict:
    out = {}
    for sid, text in R.items():
        print(f"[rb] {sid}")
        r = call(f"{BFF}/projects/{pid}/requirements", {"text": text})
        out[sid] = {"text": text, "status": r["status"], "body": r["body"]}
        print(f"   requirements={r['body'].get('requirements')} unknown={r['body'].get('unknown_symptoms')}")
        # M1 오투입(라우팅 부재) — 요구를 지식 경로에 넣으면?
        ab = call(f"{BFF}/extraction/ab", {"text": text, "providers": ["claude", "solar"]})
        claude = next((x for x in ab["body"]["results"] if x["requested_provider"] == "claude"), {})
        v = call(f"{BFF}/extraction/validate", {"concepts": claude.get("concepts", []),
                                                "relations": claude.get("relations", []), "project_id": pid})
        out[sid]["m1_misroute"] = {"concepts": claude.get("concepts", []),
                                   "relations": claude.get("relations", []), "validate": v["body"]}
        blocking = [x for x in v["body"].get("violations", []) if x["severity"] == "violation"]
        print(f"   M1 오투입: conforms={v['body'].get('conforms')} 차단={len(blocking)} "
              f"relations={[(x['subject'], x['predicate'], x['object']) for x in claude.get('relations', [])]}")
        dump("rb", out)
    return out


# ── (5) 불변: 시드 회귀 · 도메인 밖 fail-closed ──────────────────────────────
def step_invariant(pid: str) -> dict:
    out = {}
    for tag, d in (("sat-bad", SAT_BAD), ("sat-good", SAT_GOOD)):
        r = call(f"{BFF}/satisfy", {"project_id": pid, "design": d})["body"]
        out[tag] = r
        print(f"  [{tag}] satisfies={r['satisfies']} violations={r['violations']}")
    # 판정 보류(pending) — 수치 결측
    p = call(f"{BFF}/satisfy", {"project_id": pid, "design": {"material": "Rubber", "vehicle": "MidSizeSUV"}})["body"]
    out["sat-pending"] = p
    print(f"  [sat-pending] satisfies={p['satisfies']} pending={p.get('pending_reason')}")
    # 지식범위 스코프
    for tag, cats in (("scope-A", ["소음"]), ("scope-B", ["떨림"])):
        r = call(f"{BFF}/satisfy", {"project_id": pid, "design": SAT_BAD, "categories": cats})["body"]
        out[tag] = r
        print(f"  [{tag}] satisfies={r['satisfies']} violations={r['violations']}")
    # 도메인 밖 Q&A
    out["qa"] = {}
    for q in ("자전거 브레이크 패드는 왜 마모되나요?", "타이어 공기압이 낮으면 어떤 문제가 생기나요?"):
        r = call(f"{BFF}/qa", {"question": q, "mode": "verified", "project_id": pid})
        b = r["body"]
        out["qa"][q] = b
        print(f"  [qa] insufficient={b.get('insufficient_evidence')} sources={len(b['verified_answer'].get('sources', []))}")
    # 저작 우회 시도(도메인 밖 개념)
    by = call(f"{BFF}/extraction/save", {
        "sentence_text": "타이어는 겨울철에 마모된다.",
        "concepts": [{"label": "타이어", "type": "Material"}, {"label": "마모", "type": "Symptom"}],
        "relations": [{"subject": "타이어", "predicate": "causes", "object": "마모"}],
        "category": "소음", "approved": True, "project_id": pid})
    out["bypass_authoring"] = {"status": by["status"], "body": by["body"]}
    print(f"  [bypass 저작] status={by['status']}")
    out["rules_final"] = rules()
    dump("invariant", out)
    return out


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    pid = sys.argv[2] if len(sys.argv) > 2 else project()
    print(f"== step={step} pid={pid} ==")
    ab = None
    if step in ("ab", "all"):
        ab = step_ab(pid)
    if step in ("author", "all"):
        step_author(pid, ab)
    if step in ("flagship", "all"):
        step_flagship(pid)
    if step in ("rb", "all"):
        step_rb(pid)
    if step in ("invariant", "all"):
        step_invariant(pid)
    print(f"DONE pid={pid}")
