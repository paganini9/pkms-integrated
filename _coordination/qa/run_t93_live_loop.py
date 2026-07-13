"""T-93 라이브 증명 — 실 스택(Docker·Solar/Claude 실키)에서 K2 저작 전후 satisfy 판정 차이."""
from __future__ import annotations

import io
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BFF = "http://localhost:4000/api/v1"
KB = "http://localhost:8000"


def call(url: str, body=None, method=None, admin=False, timeout=180):  # noqa: ANN001, ANN201
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
            b = {"raw": raw.decode(errors="replace")[:500]}
        return {"status": e.code, "body": b, "ms": int((time.time() - t0) * 1000)}

DESIGN = {"id": "D-ozone", "material": "Rubber", "vehicle": "MidSizeSUV",
          "length_mm": 550, "spring_n": 12, "arm_shape": "complex", "env": "Ozone"}
SAT_BAD = {"material": "Rubber", "length_mm": 600, "spring_n": 8, "arm_shape": "simple",
           "vehicle": "MidSizeSUV", "env": "Winter"}
SAT_GOOD = {"material": "Silicone", "length_mm": 550, "spring_n": 12, "arm_shape": "complex",
            "vehicle": "CompactSedan", "env": "Winter"}

K2 = "오존 노출이 기준을 초과하면 고무 블레이드에 균열이 생긴다."
CONCEPTS = [
    {"label": "오존", "type": "EnvCondition"},
    {"label": "블레이드", "type": "Component"},   # LLM 오타이핑 그대로 — T-94 가 PartType 으로 해석
    {"label": "고무", "type": "Material"},
    {"label": "균열", "type": "Symptom"},
]
RELATIONS = [
    {"subject": "블레이드", "predicate": "hasMaterial", "object": "고무"},
    {"subject": "고무", "predicate": "causes", "object": "균열"},
    {"subject": "균열", "predicate": "conditionedOn", "object": "오존"},
]


def summarize(tag: str, r: dict) -> dict:
    b = r["body"]
    ex = [(e["symptom"], e["sentences"]) for e in (b.get("steps") or [{}, {}, {}])[2].get("exhibited", [])]
    print(f"  [{tag}] satisfies={b.get('satisfies')} violations={b.get('violations')} exhibited={ex}")
    return b


def main() -> None:
    pid = call(f"{BFF}/projects", {"name": "t93-live", "target_vehicle": "MidSizeSUV",
                                   "target_env": "Ozone", "knowledge_categories": ["소음", "떨림"]})["body"]["id"]
    out = {"project": pid}

    print("⓪ 거버넌스 승인 — 신규 개념 Ozone·Crack (+한글 altLabel)")
    g = call(f"{BFF}/upper-ontology/classes", {
        "approved": True,
        "changes": [{"op": "add", "id": "Ozone", "parent": "EnvCondition"},
                    {"op": "add", "id": "Crack", "parent": "Symptom"}]}, admin=True)
    print("  add:", g["status"], g["body"])
    for iri, lb in [("http://ex.org/spmm-ext#Ozone", "오존"), ("http://ex.org/spmm-ext#Crack", "균열")]:
        a = call(f"{KB}/oov/approve", {"concept_iri": iri, "label": lb, "approved": True})
        print(f"  altLabel {lb}:", a["status"])

    print("① 시드 회귀(저작 전) — 하드 게이트")
    out["seed_bad_before"] = summarize("sat-bad", call(f"{BFF}/satisfy", {"project_id": pid, "design": SAT_BAD}))
    out["seed_good_before"] = summarize("sat-good", call(f"{BFF}/satisfy", {"project_id": pid, "design": SAT_GOOD}))

    print("② K2 저작 전 — 오존 설계 판정")
    out["before"] = summarize("before", call(f"{BFF}/satisfy", {"project_id": pid, "design": DESIGN}))
    out["rules_before"] = [r["id"] for r in call(f"{KB}/rules")["body"]["rules"]]
    print("  규칙:", out["rules_before"])

    print("③ K2 저작 (검증 → 저장)")
    v = call(f"{BFF}/extraction/validate", {"concepts": CONCEPTS, "relations": RELATIONS, "project_id": pid})
    out["validate"] = v["body"]
    print("  validate conforms=", v["body"].get("conforms"),
          [(x["code"], x["severity"], x["offender"]) for x in v["body"].get("violations", [])])
    s = call(f"{BFF}/extraction/save", {"sentence_text": K2, "concepts": CONCEPTS, "relations": RELATIONS,
                                        "category": "소음", "approved": True, "draft_id": "t93-live-k2",
                                        "project_id": pid})
    out["save"] = {"status": s["status"], "body": s["body"]}
    print("  save:", s["status"])
    if s["status"] == 201:
        d = s["body"]["derived"]["rule"]
        print(f"  derived rule: id={d['id']} about_symptom={d['about_symptom']} "
              f"conds={[(c['path'], c['val']) for c in d['conds']]}")

    print("④ K2 저작 후 — 같은 설계 재판정")
    out["after"] = summarize("after", call(f"{BFF}/satisfy", {"project_id": pid, "design": DESIGN}))
    out["rules_after"] = [r["id"] for r in call(f"{KB}/rules")["body"]["rules"]]
    print("  규칙:", out["rules_after"])

    print("⑤ Causation 저장 그래프")
    q = call(f"{KB}/sparql", {"query":
        "SELECT ?c ?m ?cond ?s WHERE { ?c a <http://ex.org/spmm-ext#Causation> ; "
        "<http://ex.org/spmm-ext#hasMechanism> ?m ; <http://ex.org/spmm-ext#underCondition> ?cond ; "
        "<http://ex.org/spmm-ext#manifestsSymptom> ?s }"})
    rows = q["body"].get("rows", [])
    out["causation"] = rows
    print(f"  Causation {len(rows)} 행:", [(r["m"].split("#")[-1], r["cond"].split("#")[-1], r["s"].split("#")[-1]) for r in rows])

    print("⑥ 시드 회귀(저작 후) — 불변 확인")
    out["seed_bad_after"] = summarize("sat-bad", call(f"{BFF}/satisfy", {"project_id": pid, "design": SAT_BAD}))
    out["seed_good_after"] = summarize("sat-good", call(f"{BFF}/satisfy", {"project_id": pid, "design": SAT_GOOD}))

    out_path = pathlib.Path(__file__).resolve().parents[2] / "docs" / "postg3-원자료" / "t93_live.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out_path}")


if __name__ == "__main__":
    main()
