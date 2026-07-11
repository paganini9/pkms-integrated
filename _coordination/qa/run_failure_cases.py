#!/usr/bin/env python3
"""T-72 — 실패 케이스 실 스택 검증 (수용기준 §4, Solar 실키).

§4 실패 모드는 이미 유닛/회귀로 커버됨(참조):
  - LLM 타임아웃→Breaker 폴백: bff `reliability.test.ts`
  - 추출 range 위반→저장 차단: `ext-range`(회귀) · `spec_validate` 유닛
  - satisfy 수치 누락→판정 보류: `test_회귀_sat_pending`(knowledge)
  - reasoner 지연→시그니처 캐시: T-34 유닛
  - 트리플/벡터 불일치→롤백(원자성): `test_kg_save_atomic_rollback`(knowledge)
이 러너는 그중 **HTTP 로 관측 가능한 모드 + 도메인밖·원자성 저장을 Solar 실키로 1회** 재확인한다.

사용: python run_failure_cases.py --bff http://localhost:4001   (knowledge+Solar BFF, Studio_API_Key)
exit 1 = 실패 모드가 규정대로 동작하지 않음.
"""
from __future__ import annotations

import argparse
import sys

import httpx


def check(fails: list, name: str, cond: bool, detail: str) -> None:
    print(f"[{'OK' if cond else 'XX'}] {name:22s} {'' if cond else '← ' + detail}")
    if not cond:
        fails.append(f"{name}: {detail}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="실패 케이스 실 스택 (T-72)")
    ap.add_argument("--bff", default="http://localhost:4001")
    args = ap.parse_args()
    bff = args.bff
    fails: list[str] = []

    with httpx.Client(timeout=90) as c:
        # ── FC1: 추출 range 위반 → 저장 차단(HITL 서버측 재검증) ──
        r = c.post(f"{bff}/api/v1/extraction/save", json={
            "sentence_text": "경도가 겨울철을 유발한다",
            "category": "소음", "approved": True, "draft_id": "fc-range-1",
            "concepts": [{"label": "경도", "type": "Attribute"}, {"label": "겨울철", "type": "EnvCondition"}],
            "relations": [{"subject": "경도", "predicate": "causes", "object": "겨울철"}],
        })
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        check(fails, "range 위반 저장차단", r.status_code == 409, f"HTTP {r.status_code} 기대 409 ({str(body)[:80]})")

        # ── FC2: satisfy 수치 누락 → 판정 보류(422 아님, 200 pending) ──
        r = c.post(f"{bff}/api/v1/satisfy", json={
            "project_id": "fc", "categories": ["떨림"], "require": ["RB_NoChatter"],
            "design": {"material": "Rubber", "length_mm": 600, "arm_shape": "simple", "vehicle": "MidSizeSUV", "env": "Winter"},
        })
        b = r.json() if r.status_code == 200 else {}
        check(fails, "수치누락 판정보류", r.status_code == 200 and b.get("satisfies") is None and b.get("pending_reason") == "missing_required",
              f"HTTP {r.status_code} satisfies={b.get('satisfies')} pending={b.get('pending_reason')}")

        # ── FC3: 도메인 밖 질의 → "명세 근거 없음"(억지 답 금지) · Solar 실키 ──
        r = c.post(f"{bff}/api/v1/qa", json={"question": "엔진 오일 교환 주기는 얼마인가요?", "mode": "verified"})
        b = r.json() if r.status_code == 200 else {}
        va = b.get("verified_answer") or {}
        check(fails, "도메인밖 근거없음", b.get("insufficient_evidence") is True and (va.get("sources") or []) == [] and "명세 근거 없음" in (va.get("text") or ""),
              f"insuff={b.get('insufficient_evidence')} sources={len(va.get('sources') or [])} text={(va.get('text') or '')[:40]}")

        # ── FC4: 저장 원자성(멱등) — 같은 draft_id 재전송에 중복 저장 0 · Solar 실키로 1회 ──
        payload = {
            "sentence_text": "실리콘 블레이드는 저온에서 소음을 해소한다.",
            "category": "소음", "approved": True, "draft_id": "fc-atomic-1",
            "concepts": [{"label": "실리콘", "type": "Material"}, {"label": "소음", "type": "Symptom"}],
            "relations": [{"subject": "실리콘", "predicate": "mitigates", "object": "소음"}],
        }
        r1 = c.post(f"{bff}/api/v1/extraction/save", json=payload)
        r2 = c.post(f"{bff}/api/v1/extraction/save", json=payload)
        s1 = (r1.json().get("sentence") or {}) if r1.status_code in (200, 201) else {}
        s2 = (r2.json().get("sentence") or {}) if r2.status_code in (200, 201) else {}
        check(fails, "저장 멱등(원자성)", r1.status_code in (200, 201) and s1.get("iri") and s1.get("iri") == s2.get("iri"),
              f"r1={r1.status_code} r2={r2.status_code} iri1={s1.get('iri')} iri2={s2.get('iri')}")

    print("\n=== 실패 케이스(실 스택·Solar) " + ("통과" if not fails else "실패") + f" · 위반 {len(fails)}건 ===")
    for f in fails:
        print("  -", f)
    print("(타임아웃·Breaker·rollback 심층은 유닛 테스트 참조: reliability.test.ts · test_kg_save_atomic_rollback)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
