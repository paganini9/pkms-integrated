"""CD-10 · AC-8 — 개념 거버넌스(`/governance/concepts*`).

builtin = `api_standard.md` §3 의 `ConceptType` 8종. **builtin 삭제/수정은 400 BUILTIN_LOCKED**.
custom 개념은 트리플로 영속한다(Oxigraph 영속 스토어 → 재기동 후 유지).
생성은 HITL 게이트(불변원칙 4): `approved:true` 없으면 409 GUARDRAIL_BLOCKED.
"""
from __future__ import annotations

import pyoxigraph as ox

from core.logging import get_trace_id
from schemas.errors import BuiltinLocked, GuardrailBlocked, NotFound
from store.oxigraph import DOM, RDF_TYPE, RDFS_LABEL, OxigraphStore, _localname

# api_standard.md §3 ConceptType — 순서·라벨 고정
BUILTIN: list[tuple[str, str]] = [
    ("PartType", "부품유형"),
    ("Component", "구성요소"),
    ("Material", "재질"),
    ("VehicleType", "차종"),
    ("EnvCondition", "환경조건"),
    ("Symptom", "증상"),
    ("Behavior", "거동"),
    ("Attribute", "속성"),
]
_BUILTIN_IDS = {i for i, _ in BUILTIN}

_CONCEPT_CLASS = f"{DOM}GovernanceConcept"  # custom 개념 마커
_PARENT = f"{DOM}parentConcept"


class GovernanceService:
    """builtin/custom 개념 조회·생성·삭제."""

    def __init__(self, store: OxigraphStore) -> None:
        self.store = store

    def list(self) -> dict:
        rows = self.store.query(
            f"SELECT ?c ?label ?parent WHERE {{ ?c a <{_CONCEPT_CLASS}> ; "
            f"<{RDFS_LABEL}> ?label . OPTIONAL {{ ?c <{_PARENT}> ?parent }} }}",
            readonly=False,
        )
        custom = sorted(
            (
                {
                    "id": _localname(r["c"]),
                    "label": r.get("label", ""),
                    "parent": _localname(r["parent"]) if r.get("parent") else None,
                }
                for r in rows
            ),
            key=lambda x: x["id"],
        )
        return {
            "builtin": [{"id": i, "label": lbl} for i, lbl in BUILTIN],
            "custom": custom,
            "trace_id": get_trace_id(),
        }

    def create(self, concept_id: str, label: str, parent: str | None, approved: bool) -> dict:
        if not approved:
            raise GuardrailBlocked(internal=f"governance concept {concept_id!r} 미승인 저장 시도")
        if concept_id in _BUILTIN_IDS:
            raise BuiltinLocked(internal=f"builtin 개념 {concept_id!r} 은 재정의할 수 없음")
        node = ox.NamedNode(f"{DOM}{concept_id}")
        # 재정의 방지: 기존 custom 트리플 정리 후 재작성(멱등)
        for q in list(self.store._store.quads_for_pattern(node, None, None, None)):  # noqa: SLF001
            self.store._store.remove(q)  # noqa: SLF001
        quads = [
            ox.Quad(node, ox.NamedNode(RDF_TYPE), ox.NamedNode(_CONCEPT_CLASS)),
            ox.Quad(node, ox.NamedNode(RDFS_LABEL), ox.Literal(label)),
        ]
        if parent:
            quads.append(ox.Quad(node, ox.NamedNode(_PARENT), ox.NamedNode(f"{DOM}{parent}")))
        self.store._store.extend(quads)  # noqa: SLF001
        return {
            "id": concept_id,
            "label": label,
            "parent": parent,
            "iri": f"{DOM}{concept_id}",
            "trace_id": get_trace_id(),
        }

    def delete(self, concept_id: str) -> dict:
        if concept_id in _BUILTIN_IDS:
            raise BuiltinLocked(internal=f"builtin 개념 {concept_id!r} 삭제 시도")
        node = ox.NamedNode(f"{DOM}{concept_id}")
        existing = list(self.store._store.quads_for_pattern(node, ox.NamedNode(RDF_TYPE), ox.NamedNode(_CONCEPT_CLASS)))  # noqa: SLF001
        if not existing:
            raise NotFound(internal=f"custom 개념 {concept_id!r} 없음")
        self.store.remove_about(f"{DOM}{concept_id}")
        return {"deleted": concept_id, "trace_id": get_trace_id()}
