"""포스트-g3 실 검증 하네스 — 게이트 아님. 관찰만 하고 전부 JSON 으로 남긴다.

실행: python probe.py <step>
  step: ab | rb | route | oov | flagship | safety | all
결과: results/<step>.json
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BFF = "http://localhost:4000/api/v1"
KB = "http://localhost:8000"
OUT = Path(__file__).parent / "results"
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
    "R2": "와이퍼 가동 시 유리 표면에 물끌림이나 얼룩이 남지 않아야 한다.",
    "R3": "와이퍼 1회 왕복 후 운전자의 시야가 즉시 확보되어야 한다.",
    "R4": "고무 블레이드는 최소 50만 회 이상의 왕복 작동 후에도 초기 성능 기준을 만족해야 한다.",
    "R5": "블레이드 고무 재질은 기준치 이상의 오존 및 자외선 노출 환경에서 균열이나 경화가 발생하지 않아야 한다.",
    "R6": "영하 40도 환경에서도 고무의 유연성을 유지해야 하며 프레임 결빙으로 인한 작동 불량이 없어야 한다.",
    "R7": "워셔액·세차제·염화칼슘 등 외부 화학 물질 노출에 의한 변형이나 부식이 발생하지 않아야 한다.",
    "R8": "다양한 차량용 와이퍼 암 커넥터와 유격 없이 견고하게 체결되어 주행 중 이탈되지 않아야 한다.",
}
ALL = {**K, **R}


def call(url: str, body=None, method=None, admin=False, timeout=180):
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
        except Exception:
            b = {"raw": raw.decode(errors="replace")[:500]}
        return {"status": e.code, "body": b, "ms": int((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        return {"status": 0, "body": {"error": repr(e)}, "ms": int((time.time() - t0) * 1000)}


def dump(name: str, obj) -> None:
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {p}")


def project() -> str:
    r = call(f"{BFF}/projects", {"name": "postg3-검증", "target_vehicle": "MidSizeSUV",
                                 "target_env": "Winter", "knowledge_categories": ["소음", "떨림"]})
    pid = r["body"].get("id") or r["body"].get("project_id")
    print(f"project={pid} ({r['status']})")
    return pid


# ── 1) A/B 추출 (13문장 × solar·claude) + 검증 + 저장 시도 ──────────────────
def step_ab(pid: str):
    out = {}
    for sid, text in ALL.items():
        print(f"[ab] {sid}")
        ab = call(f"{BFF}/extraction/ab", {"text": text, "providers": ["solar", "claude"]})
        rec = {"text": text, "ab_status": ab["status"], "ms": ab["ms"], "results": {}}
        for res in ab["body"].get("results", []):
            p = res["requested_provider"]
            entry = {
                "actual_provider": res.get("actual_provider"),
                "concepts": res.get("concepts", []),
                "relations": res.get("relations", []),
                "error": res.get("error"),
            }
            # 각 provider 추출안을 그대로 검증 게이트에 태운다(제공자 무관 게이트 확인)
            v = call(f"{BFF}/extraction/validate", {
                "concepts": entry["concepts"], "relations": entry["relations"], "project_id": pid})
            entry["validate"] = v["body"]
            # 저장 시도 (HITL 승인 = true) — 차단/통과 관찰
            s = call(f"{BFF}/extraction/save", {
                "sentence_text": text, "concepts": entry["concepts"], "relations": entry["relations"],
                "category": "소음", "approved": True, "draft_id": f"pg3-{sid}-{p}", "project_id": pid})
            entry["save"] = {"status": s["status"], "body": s["body"]}
            rec["results"][p] = entry
        out[sid] = rec
        dump("ab", out)
    return out


# ── 2) M2 / RB 파싱 (요구 8문장) ────────────────────────────────────────────
def step_rb(pid: str):
    out = {}
    for sid, text in R.items():
        print(f"[rb] {sid}")
        r = call(f"{BFF}/projects/{pid}/requirements", {"text": text})
        out[sid] = {"text": text, "status": r["status"], "body": r["body"], "ms": r["ms"]}
        dump("rb", out)
    # 전체를 한 번에 넣어보기 (여러 요구 동시 파싱 능력)
    joined = " ".join(R.values())
    r = call(f"{BFF}/projects/{pid}/requirements", {"text": joined})
    out["_ALL8"] = {"text": joined, "status": r["status"], "body": r["body"], "ms": r["ms"]}
    dump("rb", out)
    return out


# ── 3) 라우팅 프로브: R5·R1 을 M1(SmartInput) 경로에 투입 ────────────────────
def step_route(pid: str):
    out = {}
    for sid in ("R1", "R5"):
        text = R[sid]
        print(f"[route] {sid} → M1 stream")
        # SSE 스트림 원문 캡처
        req = urllib.request.Request(f"{BFF}/extraction/stream", data=json.dumps(
            {"text": text, "project_id": pid}).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        events = []
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                cur = {}
                for raw in r:
                    line = raw.decode("utf-8").rstrip("\n")
                    if line.startswith("event: "):
                        cur["event"] = line[7:]
                    elif line.startswith("data: "):
                        cur["data"] = json.loads(line[6:])
                    elif line == "" and cur:
                        events.append(cur)
                        cur = {}
        except Exception as e:  # noqa: BLE001
            events.append({"event": "_transport_error", "data": repr(e)})
        out[sid] = {"text": text, "events": events}
        dump("route", out)
    return out


# ── 4) OOV 트리아지 ────────────────────────────────────────────────────────
def step_oov(labels: list[str]):
    out = {}
    for lb in labels:
        print(f"[oov] {lb}")
        r = call(f"{BFF}/oov/triage", {"label": lb, "k": 3})
        out[lb] = {"status": r["status"], "body": r["body"]}
        dump("oov", out)
    return out


# ── 5) 플래그십 루프: K2 → OOV 승인(오존·균열) → R5 → 설계 → satisfy ─────────
def step_flagship(pid: str):
    out = {}
    text = K["K2"]
    # (a) 저작 전 검증 — 오존·균열이 OOV 인가
    ab = call(f"{BFF}/extraction/ab", {"text": text, "providers": ["claude", "solar"]})
    claude = next((r for r in ab["body"].get("results", []) if r["requested_provider"] == "claude"), {})
    concepts, relations = claude.get("concepts", []), claude.get("relations", [])
    out["1_k2_extract"] = {"concepts": concepts, "relations": relations}
    out["2_k2_validate_before"] = call(f"{BFF}/extraction/validate", {
        "concepts": concepts, "relations": relations, "project_id": pid})["body"]

    # (b) 신규 개념 편입 — 상위 온톨로지 클래스 신설(T-85 오버레이, admin)
    out["3_upper_add"] = call(f"{BFF}/upper-ontology/classes", {
        "approved": True,
        "changes": [{"op": "add", "id": "Ozone", "parent": "EnvCondition"},
                    {"op": "add", "id": "Crack", "parent": "Symptom"}],
    }, admin=True)

    # (c) 한글 표면어 편입 — altLabel 승인. BFF 표면이 없으면 지식서비스 직접(경계 갭 관찰).
    out["4_oov_approve_bff"] = call(f"{BFF}/oov/approve", {
        "concept_iri": "Ozone", "label": "오존", "approved": True}, admin=True)
    out["4b_oov_approve_direct"] = [
        call(f"{KB}/oov/approve", {"concept_iri": "Ozone", "label": "오존", "approved": True}),
        call(f"{KB}/oov/approve", {"concept_iri": "Crack", "label": "균열", "approved": True}),
        call(f"{KB}/oov/approve", {"concept_iri": "Crack", "label": "크랙", "approved": True}),
    ]

    # (d) 편입 후 재검증 — 오존·균열이 접지되는가
    out["5_k2_validate_after"] = call(f"{BFF}/extraction/validate", {
        "concepts": concepts, "relations": relations, "project_id": pid})["body"]
    out["5b_oov_triage_after"] = {lb: call(f"{BFF}/oov/triage", {"label": lb})["body"]
                                  for lb in ("오존", "균열")}
    out["5c_save_after"] = call(f"{BFF}/extraction/save", {
        "sentence_text": text, "concepts": concepts, "relations": relations,
        "category": "소음", "approved": True, "draft_id": "pg3-flagship-k2", "project_id": pid})

    # (e) R5 를 RB 로 저작
    out["6_r5_rb"] = call(f"{BFF}/projects/{pid}/requirements", {"text": R["R5"]})

    # (f) 설계 인스턴스 → satisfy
    out["7_satisfy"] = call(f"{BFF}/satisfy", {
        "project_id": pid,
        "design": {"id": "D-ozone", "material": "Rubber", "vehicle": "MidSizeSUV",
                   "length_mm": 650, "spring_n": 12, "arm_shape": "simple", "env": "Winter"},
        "require": [],
    })
    # 설계에 오존 노출을 표현할 수 있는가 — 스키마 밖 필드 투입
    out["8_satisfy_ozone_field"] = call(f"{BFF}/satisfy", {
        "project_id": pid,
        "design": {"id": "D-ozone2", "material": "Rubber", "vehicle": "MidSizeSUV", "ozone_ppm": 120},
        "require": [],
    })
    # 규칙 뷰 — 편입된 개념이 규칙/게이트를 만드는가
    out["9_rules"] = call(f"{BFF}/rules", admin=True)["body"]
    out["10_graph_M1"] = call(f"{BFF}/graph?layer=M1&limit=200")["body"]
    dump("flagship", out)
    return out


# ── 6) 안전: 도메인 밖 · 우회 ───────────────────────────────────────────────
def step_safety(pid: str):
    out = {"qa": {}, "bypass": {}}
    for q in ["자전거 브레이크 패드는 왜 마모되나요?",
              "타이어 공기압이 낮으면 어떤 문제가 생기나요?",
              "겨울철에 와이퍼 소음이 왜 생기나요?"]:
        print(f"[qa] {q}")
        r = call(f"{BFF}/qa", {"question": q, "mode": "verified", "project_id": pid})
        out["qa"][q] = {"status": r["status"], "body": r["body"]}
        dump("safety", out)
    # 우회 시도: 도메인 밖 개념을 지식으로 저장
    bypass = [
        {"name": "타이어 고무 저장", "sentence_text": "타이어 고무는 겨울철에 균열이 생긴다.",
         "concepts": [{"label": "타이어 고무", "type": "Material"}, {"label": "균열", "type": "Symptom"}],
         "relations": [{"subject": "타이어 고무", "predicate": "causes", "object": "균열"}]},
        {"name": "위조 violations(range 위반)", "sentence_text": "고무는 고무를 유발한다.",
         "concepts": [{"label": "고무", "type": "Material"}],
         "relations": [{"subject": "고무", "predicate": "causes", "object": "고무"}]},
    ]
    for b in bypass:
        r = call(f"{BFF}/extraction/save", {
            "sentence_text": b["sentence_text"], "concepts": b["concepts"], "relations": b["relations"],
            "category": "소음", "approved": True, "project_id": pid})
        out["bypass"][b["name"]] = {"status": r["status"], "body": r["body"]}
        dump("safety", out)
    return out


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    pid = sys.argv[2] if len(sys.argv) > 2 else project()
    print(f"== step={step} pid={pid} ==")
    if step in ("ab", "all"):
        step_ab(pid)
    if step in ("rb", "all"):
        step_rb(pid)
    if step in ("route", "all"):
        step_route(pid)
    if step in ("flagship", "all"):
        step_flagship(pid)
    if step in ("safety", "all"):
        step_safety(pid)
    if step.startswith("oov:"):
        step_oov(step.split(":", 1)[1].split(","))
    print(f"DONE pid={pid}")
