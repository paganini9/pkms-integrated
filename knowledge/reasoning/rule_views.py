"""CD-10 · FR-13 — 규칙 **읽기 전용** 조회 뷰(`GET /rules`, `GET /rules/{id}/impact`).

PUT/PATCH 는 없다 — 규칙은 문장 파생물이다(FR-3d). 편집은 문장 수정 → 재파생이다.

- `GET /rules`             : `rules/compile` 의 조회판(전체 카테고리). rules·shapes·human_view.
- `GET /rules/{id}/impact` : 그 규칙의 SHACL 게이트가 실제로 발화하는 **M2 설계 인스턴스** 목록.
  게이트가 없는 규칙(mitigate)은 발화 대상이 없으므로 빈 목록이다. 근사가 아니라 실제 pySHACL 발화다.
"""
from __future__ import annotations

from rdflib import Graph

from core.logging import get_trace_id
from reasoning.rules import loc
from reasoning.satisfy import SatisfyEngine
from schemas.errors import NotFound


class RuleViews:
    def __init__(self, engine: SatisfyEngine) -> None:
        self.engine = engine
        self.compiler = engine.compiler

    def list(self) -> dict:
        compiled = self.compiler.compile(None)  # 전체
        rules = [
            {
                "id": r.id,
                "label": r.label,
                "polarity": r.polarity,
                "category": r.category,
                "basis": r.basis,
                "about_symptom": r.symptom,
                "makes_gate": r.makes_gate,
            }
            for r in compiled.applied_rules
        ]
        return {
            "rules": rules,
            "shapes": sorted(compiled.gates),
            "human_view": compiled.human_view,
            "trace_id": get_trace_id(),
        }

    def impact(self, rule_id: str) -> dict:
        compiled = self.compiler.compile(None)
        rule = next((r for r in compiled.applied_rules if r.id == rule_id), None)
        if rule is None:
            raise NotFound(internal=f"규칙 {rule_id!r} 없음")

        if not rule.makes_gate:
            # mitigate 규칙은 게이트가 없다 — 발화 대상 없음(억지로 만들지 않는다).
            return {"affected_instances": [], "trace_id": get_trace_id()}

        shape_id = rule.shape_id
        data = Graph()
        for t in self.engine._onto:  # noqa: SLF001 — 같은 레이어
            data.add(t)
        for t in self.engine._m2:  # noqa: SLF001
            data.add(t)
        by_focus = self.engine._run_gates(data, compiled)  # noqa: SLF001

        affected = sorted(
            loc(focus)
            for focus, shapes in by_focus.items()
            if shape_id in shapes and str(focus).startswith("http://ex.org/eng#")
        )
        return {"affected_instances": affected, "trace_id": get_trace_id()}
