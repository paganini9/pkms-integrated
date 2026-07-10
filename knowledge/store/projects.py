"""프로젝트 CRUD + 지식범위(knowledge_categories) + 요구사항(RB) 저장.

M2 그래프에 `dom:Project`·`dom:hasRequirement`·`dom:targetVehicle`·`dom:targetEnv`·`dom:hasDesign`
구조로 저장한다(m2_instances.ttl 의 eng:Proj_WinterSUV 형태를 따른다).

`knowledge-scope` 의 `compiled_gates` 는 RuleCompiler 주입으로 계산하되, 미완이면
rules.ttl 에서 **극성이 cause·aggravate 인** 규칙 중 해당 카테고리 수를 센다
(mitigate 는 게이트를 만들지 않는다 — gen_shacl.compile_rules 와 동일 규칙).
"""
from __future__ import annotations

import uuid

import pyoxigraph as ox

from core.logging import get_trace_id
from schemas.errors import NotFound
from schemas.models import (
    KnowledgeScopeResponse,
    Requirement,
)
from store.oxigraph import (
    DOM,
    ENG,
    RDF_TYPE,
    RDFS_LABEL,
    SPMM,
    OxigraphStore,
    _localname,
)

_PROJ_ID = f"{DOM}projectId"
_KNOW_CAT = f"{DOM}knowledgeCategory"  # 지식범위(카테고리) 저장용 커스텀 술어


class ProjectService:
    """M2 프로젝트 데이터의 저장/조회."""

    def __init__(self, store: OxigraphStore, rule_compiler=None) -> None:  # noqa: ANN001
        self.store = store
        self.rule_compiler = rule_compiler

    # ── 생성 ────────────────────────────────────────────────────────────
    def create(
        self,
        name: str,
        target_vehicle: str,
        knowledge_categories: list[str],
        target_env: str | None = None,
    ) -> dict:
        pid = uuid.uuid4().hex
        iri = f"{ENG}Proj_{pid[:8]}"
        node = ox.NamedNode(iri)
        quads = [
            ox.Quad(node, ox.NamedNode(RDF_TYPE), ox.NamedNode(f"{DOM}Project")),
            ox.Quad(node, ox.NamedNode(_PROJ_ID), ox.Literal(pid)),
            ox.Quad(node, ox.NamedNode(RDFS_LABEL), ox.Literal(name)),
            ox.Quad(node, ox.NamedNode(f"{DOM}targetVehicle"), ox.NamedNode(f"{DOM}{target_vehicle}")),
        ]
        if target_env:
            quads.append(
                ox.Quad(node, ox.NamedNode(f"{DOM}targetEnv"), ox.NamedNode(f"{DOM}{target_env}"))
            )
        for cat in knowledge_categories:
            quads.append(ox.Quad(node, ox.NamedNode(_KNOW_CAT), ox.Literal(cat)))
        self.store._store.extend(quads)  # noqa: SLF001 — 같은 패키지 내부 접근
        return self.get(pid)

    # ── 조회 ────────────────────────────────────────────────────────────
    def _iri_of(self, project_id: str) -> str:
        esc = project_id.replace('"', '\\"')
        rows = self.store.query(
            f'SELECT ?p WHERE {{ ?p <{_PROJ_ID}> "{esc}" }}', readonly=False
        )
        if not rows:
            raise NotFound(internal=f"project {project_id} not found")
        return rows[0]["p"]

    def get(self, project_id: str) -> dict:
        iri = self._iri_of(project_id)
        meta = self.store.query(
            f"SELECT ?name ?veh ?env WHERE {{ "
            f"<{iri}> <{RDFS_LABEL}> ?name . "
            f"OPTIONAL {{ <{iri}> <{DOM}targetVehicle> ?veh }} "
            f"OPTIONAL {{ <{iri}> <{DOM}targetEnv> ?env }} }}",
            readonly=False,
        )
        m = meta[0] if meta else {}
        cats = [
            r["c"]
            for r in self.store.query(
                f"SELECT ?c WHERE {{ <{iri}> <{_KNOW_CAT}> ?c }}", readonly=False
            )
        ]
        requirements = self._requirements(iri)
        designs = self._designs(iri)
        return {
            "id": project_id,
            "iri": iri,
            "name": m.get("name", ""),
            "target_vehicle": _localname(m["veh"]) if m.get("veh") else None,
            "target_env": _localname(m["env"]) if m.get("env") else None,
            "knowledge_categories": cats,
            "requirements": requirements,
            "designs": designs,
            "trace_id": get_trace_id(),
        }

    def _requirements(self, iri: str) -> list[dict]:
        rows = self.store.query(
            f"SELECT ?rb ?label ?sym WHERE {{ <{iri}> <{DOM}hasRequirement> ?rb . "
            f"OPTIONAL {{ ?rb <{RDFS_LABEL}> ?label }} "
            f"OPTIONAL {{ ?rb <{DOM}forbidsSymptom> ?sym }} }}",
            readonly=False,
        )
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "id": _localname(r["rb"]),
                    "iri": r["rb"],
                    "label": r.get("label", ""),
                    "forbids_symptom": _localname(r["sym"]) if r.get("sym") else "",
                }
            )
        return out

    def _designs(self, iri: str) -> list[str]:
        rows = self.store.query(
            f"SELECT ?d WHERE {{ <{iri}> <{DOM}hasDesign> ?d }}", readonly=False
        )
        return [r["d"] for r in rows]

    # ── 지식범위 ────────────────────────────────────────────────────────
    def set_knowledge_scope(self, project_id: str, categories: list[str]) -> KnowledgeScopeResponse:
        iri = self._iri_of(project_id)
        node = ox.NamedNode(iri)
        # 기존 카테고리 제거 후 재설정
        for q in list(self.store._store.quads_for_pattern(node, ox.NamedNode(_KNOW_CAT), None, None)):  # noqa: SLF001
            self.store._store.remove(q)  # noqa: SLF001
        self.store._store.extend(  # noqa: SLF001
            [ox.Quad(node, ox.NamedNode(_KNOW_CAT), ox.Literal(c)) for c in categories]
        )
        gates = self._count_gates(set(categories))
        return KnowledgeScopeResponse(
            categories=list(categories), compiled_gates=gates, trace_id=get_trace_id()
        )

    def _count_gates(self, categories: set[str]) -> int:
        """이 범위로 컴파일되는 SHACL NodeShape 수.

        RuleCompiler 주입 시 위임하고, 미완이면 rules.ttl 에서 극성 cause·aggravate 이고
        카테고리가 범위에 든 규칙 수를 센다(mitigate 는 게이트 없음).
        """
        if self.rule_compiler is not None:
            try:
                compiled = self.rule_compiler.compile(categories)
                from rdflib import RDF, Namespace

                sh = Namespace("http://www.w3.org/ns/shacl#")
                return len(list(compiled.shapes.subjects(RDF.type, sh.NodeShape)))
            except Exception:  # noqa: BLE001 — 폴백으로
                pass
        rows = self.store.query(
            f"SELECT ?r ?pol ?cat WHERE {{ ?r a <{DOM}DesignRule> ; "
            f"<{DOM}polarity> ?pol ; <{DOM}category> ?cat }}",
            readonly=False,
        )
        return sum(
            1
            for r in rows
            if r.get("pol") in ("cause", "aggravate") and r.get("cat") in categories
        )

    # ── 요구사항(이미 파싱된 RB 배열 저장) ──────────────────────────────
    def add_requirements(self, project_id: str, requirements: list) -> dict:
        iri = self._iri_of(project_id)
        proj = ox.NamedNode(iri)
        # dict 로 들어와도 Requirement 로 강제(라우터·직접 호출 양쪽 지원)
        reqs = [r if isinstance(r, Requirement) else Requirement.model_validate(r) for r in requirements]
        quads: list = []
        for rb in reqs:
            rb_iri = rb.iri or f"{ENG}{rb.id}"
            rb_node = ox.NamedNode(rb_iri)
            quads += [
                ox.Quad(proj, ox.NamedNode(f"{DOM}hasRequirement"), rb_node),
                ox.Quad(rb_node, ox.NamedNode(RDF_TYPE), ox.NamedNode(f"{SPMM}RequiredBehavior")),
                ox.Quad(rb_node, ox.NamedNode(RDFS_LABEL), ox.Literal(rb.label)),
                ox.Quad(
                    rb_node,
                    ox.NamedNode(f"{DOM}forbidsSymptom"),
                    ox.NamedNode(f"{DOM}{rb.forbids_symptom}"),
                ),
            ]
        self.store._store.extend(quads)  # noqa: SLF001
        return {"requirements": self._requirements(iri), "trace_id": get_trace_id()}
