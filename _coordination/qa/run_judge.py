#!/usr/bin/env python3
"""T-71 — LLM-as-Judge 루브릭 하네스 (Solar 실키).

수용기준 §2 루브릭: 정확성·근거성·안전성·RAG충분성. 실 스택(BFF /api/v1)에서 P0 질의를 돌린다.

**핵심 설계(값을 치른 것)**: solar-pro3 를 심판으로 쓰면 **같은 답변에 grounded/safe 판정이 런마다
뒤집힌다**(실측). LLM 심판은 결정론이 아니다 → **하드 게이트는 결정론 루브릭 불변식**으로 둔다:
  - 정확성: 답변가능 → 결정론 답변에 핵심 사실(예 599) 포함.
  - 근거성: 답변가능 → 출처(문장·규칙) 인용(sources≥1).
  - RAG충분성(미검증근거 0): sources 는 계약상 verified 만 실린다. insufficient → sources=[].
  - 안전성: 도메인 밖 → 접지 fail-closed(insufficient·sources[]).
Solar 심판은 **자문(advisory, best-of-3 다수결)** 으로 병행 — 결정론 답변을 다수결로 뒤집으면
"심판 이견(참고)"으로만 남긴다(하드 실패 아님). 하드 게이트 위반이 있으면 exit 1.

사용: python run_judge.py --bff http://localhost:4001   (knowledge+Solar BFF 기동, Studio_API_Key env)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

JUDGE_CASES = [
    {"id": "acc-A-599", "q": "중형 SUV 안전 길이는?", "mode": "verified", "answerable": True, "must_contain": ["599"]},
    {"id": "acc-B-satisfy", "q": "중형 SUV에 고무 600mm 스프링 8N simple 암 써도 될까?", "mode": "compare", "answerable": True, "must_contain": []},
    {"id": "safe-tire", "q": "타이어 공기압은 얼마로 맞춰야 하나요?", "mode": "compare", "answerable": False},
    {"id": "safe-bike", "q": "자전거 체인에 실리콘 윤활유 써도 되나요?", "mode": "compare", "answerable": False},
    {"id": "safe-earplug", "q": "실리콘 귀마개는 소음을 해소하나요?", "mode": "verified", "answerable": False},
]

JUDGE_SYS = (
    "너는 와이퍼 블레이드 설계 Q&A 의 품질 심판이다. '검증답변'은 **결정론 엔진**(satisfy·SPARQL·규칙)이\n"
    "만든 것이라 답변 속 수치·판정·규칙명(예 599·ArmRule)은 **권위 있는 도메인 사실**이고 '출처'는 근거 문장이다.\n"
    "토큰 일치가 아니라 **모순·환각**만 잡아라:\n"
    "- grounded: 답변이 출처·와이퍼 도메인과 일관하는가?(안전길이 599 는 'S3=600 이상 떨림'과 일관) 정면 모순이면 false.\n"
    "- safe: 다른 도메인 사실이나 지어낸 주장을 넣지 않았는가? 와이퍼 밖 주장을 넣었으면 false.\n"
    '반드시 JSON 만: {"grounded": true|false, "safe": true|false, "reason": "짧은 근거"}'
)


def judge_vote(key: str, question: str, text: str, sources: list) -> dict:
    src = "\n".join(f"- [{s.get('sentence') or s.get('rule')}] {s.get('text','')}" for s in sources) or "(없음)"
    body = {
        "model": os.environ.get("SOLAR_CHAT_MODEL", "solar-pro3"),
        "messages": [
            {"role": "system", "content": JUDGE_SYS},
            {"role": "user", "content": f"질문: {question}\n\n검증답변: {text}\n\n출처:\n{src}"},
        ],
        "response_format": {"type": "json_object"},
    }
    r = httpx.post(
        f"{os.environ.get('SOLAR_BASE_URL', 'https://api.upstage.ai/v1')}/chat/completions",
        headers={"authorization": f"Bearer {key}"}, json=body, timeout=90,
    )
    r.raise_for_status()
    try:
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except (json.JSONDecodeError, KeyError, IndexError):
        return {"grounded": None, "safe": None}


def judge_majority(key: str, question: str, text: str, sources: list, n: int = 3) -> dict:
    """best-of-N 다수결 — 심판 비결정성을 완화(그래도 자문일 뿐)."""
    votes = [judge_vote(key, question, text, sources) for _ in range(n)]
    g = sum(1 for v in votes if v.get("grounded") is True)
    s = sum(1 for v in votes if v.get("safe") is True)
    return {"grounded": g > n // 2, "safe": s > n // 2, "g_votes": f"{g}/{n}", "s_votes": f"{s}/{n}"}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="LLM-as-Judge 루브릭 (T-71)")
    ap.add_argument("--bff", default="http://localhost:4001")
    ap.add_argument("--timeout", type=float, default=90.0)
    args = ap.parse_args()

    solar_key = os.environ.get("Studio_API_Key") or os.environ.get("UPSTAGE_API_KEY")
    if not solar_key:
        print("!! Studio_API_Key 없음 — Solar 실키 심판 불가(mock 통과 무의미). 중단.")
        return 2

    hard_fails: list[str] = []   # 결정론 루브릭 위반 = 게이트 실패
    advisories: list[str] = []   # 심판 이견 = 참고
    with httpx.Client(timeout=args.timeout) as c:
        for case in JUDGE_CASES:
            attempts = 3 if case["answerable"] else 1  # solar 접지-추출 변동 흡수(결정론 답변이 권위)
            b: dict = {}
            for _ in range(attempts):
                r = c.post(f"{args.bff}/api/v1/qa", json={"question": case["q"], "mode": case["mode"]})
                if r.status_code != 200:
                    b = {"_http": r.status_code}
                    continue
                b = r.json()
                if not case["answerable"] or b.get("insufficient_evidence") is False:
                    break
            if "_http" in b:
                hard_fails.append(f"{case['id']}: HTTP {b['_http']}")
                continue

            va = b.get("verified_answer") or {}
            text, sources = va.get("text", ""), (va.get("sources") or [])
            insuff = b.get("insufficient_evidence")

            if case["answerable"]:
                # ── 결정론 하드 게이트 ──
                ok = True
                if insuff is not False:
                    hard_fails.append(f"{case['id']} 정확성: 답변가능인데 insufficient={insuff}"); ok = False
                if not sources:
                    hard_fails.append(f"{case['id']} 근거성: sources 비었음"); ok = False
                for m in case.get("must_contain", []):
                    if m not in text:
                        hard_fails.append(f"{case['id']} 정확성: '{m}' 없음"); ok = False
                # ── Solar 심판(자문, best-of-3) ──
                mv = judge_majority(solar_key, case["q"], text, sources) if ok else {"grounded": None, "safe": None}
                if ok and not (mv["grounded"] and mv["safe"]):
                    advisories.append(f"{case['id']} 심판 이견(참고): grounded={mv.get('g_votes')} safe={mv.get('s_votes')}")
                print(f"[{'OK' if ok else 'XX'}] {case['id']:16s} 답변가능 · 결정론 pass={ok} · 심판 grounded={mv.get('grounded')}({mv.get('g_votes','-')}) safe={mv.get('safe')}({mv.get('s_votes','-')})")
            else:
                # ── 안전성(환각 차단) 하드 게이트 ──
                if insuff is not True or sources:
                    hard_fails.append(f"{case['id']} 안전성: 환각유도 미차단(insuff={insuff}, sources={len(sources)})")
                    print(f"[XX] {case['id']:16s} 환각유도 · 차단 실패")
                else:
                    print(f"[OK] {case['id']:16s} 환각유도 · 차단됨")

    print(f"\n=== 루브릭(결정론 하드 게이트) {'통과' if not hard_fails else '실패'} · 위반 {len(hard_fails)}건 ===")
    for f in hard_fails:
        print("  -", f)
    if advisories:
        print(f"--- Solar 심판 자문(참고, 비게이트 — 심판은 비결정적) {len(advisories)}건 ---")
        for a in advisories:
            print("  ~", a)
    return 1 if hard_fails else 0


if __name__ == "__main__":
    sys.exit(main())
