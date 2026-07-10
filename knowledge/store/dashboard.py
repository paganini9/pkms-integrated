"""CD-10 · FR-16 — `GET /dashboard`. M0/M1/M2 카운트 + 최근 활동.

카운트는 그래프 빌더(같은 진실원)에서 유도해 `/graph` 와 어긋나지 않게 한다.
`recent` 는 **런타임에 저장된** 문장·프로젝트의 `dom:createdAt` 만 쓴다 — 시드는 적재 시각을
모르므로 넣지 않는다(가짜 타임스탬프를 만들지 않는다). 저장분이 없으면 빈 배열이다.
"""
from __future__ import annotations

from rdflib import OWL, RDF, RDFS, Graph, Namespace

from core.logging import get_trace_id
from store.graph import GraphBuilder
from store.oxigraph import OxigraphStore, _localname

SPMM = Namespace("http://ex.org/spmm#")
EXT = Namespace("http://ex.org/spmm-ext#")
DOM = Namespace("http://ex.org/domain#")  # rdflib 속성 접근용 Namespace (oxigraph.DOM 은 str)


class DashboardService:
    def __init__(self, store: OxigraphStore) -> None:
        self.store = store

    def summary(self) -> dict:
        g = self.store.to_rdflib()
        graph = GraphBuilder(self.store).build(limit=10_000)  # 카운트용 — 절단 없이

        by = {"M0": {}, "M1": {}, "M2": {}}
        for n in graph.nodes:
            layer = n.layer or "M1"
            by.setdefault(layer, {})
            by[layer][n.kind] = by[layer].get(n.kind, 0) + 1

        m0_relations = sum(
            1
            for p in set(g.subjects(RDF.type, OWL.ObjectProperty))
            if str(p).startswith(str(SPMM)) or str(p).startswith(str(EXT))
        )

        return {
            "m0": {"classes": by["M0"].get("class", 0), "relations": m0_relations},
            "m1": {
                "sentences": by["M1"].get("sentence", 0),
                "rules": by["M1"].get("rule", 0),
                "concepts": by["M1"].get("concept", 0) + by["M1"].get("symptom", 0),
            },
            "m2": {
                "projects": by["M2"].get("class", 0),
                "designs": by["M2"].get("design", 0),
                "violations": self._violation_count(g),
            },
            "recent": self._recent(g),
            "trace_id": get_trace_id(),
        }

    def _recent(self, g: Graph, limit: int = 10) -> list[dict]:
        items: list[dict] = []
        for s, at in g.subject_objects(DOM.createdAt):
            types = set(g.objects(s, RDF.type))
            if DOM.KnowledgeSentence in types:
                kind = "sentence"
            elif DOM.Project in types:
                kind = "project"
            else:
                kind = "node"
            lbl = g.value(s, DOM.sentenceText) or g.value(s, RDFS.label)
            items.append(
                {
                    "kind": kind,
                    "id": _localname(str(s)),
                    "label": str(lbl) if lbl else _localname(str(s)),
                    "at": str(at),
                }
            )
        # 최신순(내림차순). at 동률이면 id 로 안정 정렬.
        items.sort(key=lambda x: (x["at"], x["id"]), reverse=True)
        return items[:limit]

    def _violation_count(self, g: Graph) -> int:
        """저장된 설계 인스턴스가 시드 SHACL 게이트를 위반하는 (설계·게이트) 건수.

        기본 시드에는 설계 인스턴스(eng:*)가 없어 0 이다(M2 는 API 로 생성). 정직하게 계산한다.
        """
        designs = [s for s in g.subjects(RDF.type, DOM.WiperBlade) if str(s).startswith("http://ex.org/eng#")]
        if not designs:
            return 0
        try:
            import pyshacl

            from core.config import settings

            shapes = Graph().parse(settings.ontology_dir / "shapes.ttl", format="turtle")
            _c, report, _t = pyshacl.validate(
                data_graph=g, shacl_graph=shapes, inference="none", advanced=True, meta_shacl=False
            )
            sh = Namespace("http://www.w3.org/ns/shacl#")
            focuses = [report.value(r, sh.focusNode) for r in report.subjects(RDF.type, sh.ValidationResult)]
            return sum(1 for f in focuses if f in designs)
        except Exception:  # noqa: BLE001 — 대시보드는 검증 실패로 죽지 않는다
            return 0
