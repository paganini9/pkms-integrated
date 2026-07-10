"""CD-10 — `GET /graph`. 노드·엣지·통계(추론 엣지 표시)를 스토어에서 조립한다.

불변원칙 2(내부 구조 비노출): 블랭크노드·트리플 원문은 흘리지 않는다. 노드는 명명 IRI 만,
엣지는 화이트리스트 술어만. `inferred:true` 는 **실제 추론으로 생긴 엣지**다 — 여기서는
`owl:TransitiveProperty`(시드의 `spmm:has_subbehavior`)의 이행 폐포 중 **명시되지 않은** 엣지를
계산해 표시한다. 가짜로 채우지 않으며, 추론 엣지가 없으면 `inferred_edges: 0` 이다.

결정론(NFR): 노드·엣지는 항상 정렬해 반환한다(SPARQL 결과 순서에 의존하지 않는다).
"""
from __future__ import annotations

from dataclasses import dataclass

from rdflib import OWL, RDF, RDFS, Graph, Namespace, URIRef
from rdflib.term import BNode, Literal

from core.logging import get_trace_id
from schemas.models import GraphEdge, GraphNode, GraphResponse, GraphStats
from store.oxigraph import DOM, ENG, OxigraphStore, _localname

SPMM = Namespace("http://ex.org/spmm#")
EXT = Namespace("http://ex.org/spmm-ext#")
DOM_NS = Namespace("http://ex.org/domain#")  # oxigraph.DOM 은 str — rdflib 속성 접근엔 Namespace 가 필요하다

# 지식맵에 실을 엣지 술어(화이트리스트). rdf:type·rdfs:label·sentenceText 등은 노드 속성이라 제외.
_EDGE_PREDICATES: dict[str, str] = {
    f"{DOM}mentions": "mentions",
    f"{DOM}aboutSymptom": "aboutSymptom",
    f"{DOM}derivesRule": "derivesRule",
    f"{DOM}fromSentence": "fromSentence",
    f"{DOM}hasMaterial": "hasMaterial",
    f"{DOM}mountedOn": "mountedOn",
    f"{DOM}operatesIn": "operatesIn",
    f"{DOM}targetVehicle": "targetVehicle",
    f"{DOM}targetEnv": "targetEnv",
    f"{DOM}hasRequirement": "hasRequirement",
    f"{DOM}hasDesign": "hasDesign",
    f"{DOM}forbidsSymptom": "forbidsSymptom",
    f"{EXT}causes": "causes",
    f"{EXT}mitigates": "mitigates",
    f"{EXT}aggravates": "aggravates",
    f"{EXT}conditionedOn": "conditionedOn",
    f"{SPMM}has_subbehavior": "has_subbehavior",
    f"{SPMM}satisfy_beh_required": "satisfy_beh_required",
    str(RDFS.subClassOf): "subClassOf",
}


@dataclass
class _Node:
    id: str
    label: str
    kind: str
    iri: str
    layer: str | None
    inferred: bool = False
    text: str | None = None


def _sentence_sort_key(code: str) -> tuple[int, str]:
    digits = "".join(ch for ch in code if ch.isdigit())
    return (int(digits) if digits else 1 << 30, code)


class GraphBuilder:
    """스토어 스냅샷(rdflib)에서 노드·엣지를 유도한다."""

    def __init__(self, store: OxigraphStore) -> None:
        self.store = store

    def build(
        self,
        layer: str | None = None,
        symptom: str | None = None,
        sentence: str | None = None,
        project_id: str | None = None,
        limit: int = 500,
    ) -> GraphResponse:
        g = self.store.to_rdflib()
        nodes = self._nodes(g)
        edges, _inferred = self._edges(g, nodes)

        # ── 필터 ──────────────────────────────────────────────────────────
        seeds = self._seed_ids(nodes, symptom, sentence, project_id)
        if seeds is not None:
            keep = self._neighborhood(seeds, edges, depth=2)
            nodes = {nid: n for nid, n in nodes.items() if nid in keep}
        if layer is not None:
            nodes = {nid: n for nid, n in nodes.items() if n.layer == layer}

        node_ids = set(nodes)
        edges = [e for e in edges if e.source in node_ids and e.target in node_ids]

        # ── limit (노드 기준, 결정론적 정렬 후 절단) ──────────────────────────
        truncated = False
        ordered = sorted(nodes.values(), key=lambda n: (n.layer or "", n.kind, n.id))
        if len(ordered) > limit:
            ordered = ordered[:limit]
            truncated = True
            kept = {n.id for n in ordered}
            edges = [e for e in edges if e.source in kept and e.target in kept]

        edges.sort(key=lambda e: (e.source, e.predicate, e.target))
        inferred_edges = sum(1 for e in edges if e.inferred)

        out_nodes = [
            GraphNode(
                id=n.id, label=n.label, kind=n.kind, iri=n.iri,
                layer=n.layer, inferred=n.inferred, text=n.text,
            )
            for n in ordered
        ]
        return GraphResponse(
            nodes=out_nodes,
            edges=edges,
            stats=GraphStats(
                nodes=len(out_nodes), edges=len(edges),
                inferred_edges=inferred_edges, truncated=truncated,
            ),
            trace_id=get_trace_id(),
        )

    # ── 노드 유도 ──────────────────────────────────────────────────────────
    def _nodes(self, g: Graph) -> dict[str, _Node]:
        nodes: dict[str, _Node] = {}

        def label_of(iri: URIRef) -> str:
            lbl = g.value(iri, RDFS.label)
            return str(lbl) if lbl else _localname(str(iri))

        # M1 문장
        for s in g.subjects(RDF.type, DOM_NS.KnowledgeSentence):
            if isinstance(s, BNode):
                continue
            code = _localname(str(s))
            text = g.value(s, DOM_NS.sentenceText)
            nodes[code] = _Node(code, code, "sentence", str(s), "M1", text=str(text) if text else None)

        # M1 규칙
        for s in g.subjects(RDF.type, DOM_NS.DesignRule):
            if isinstance(s, BNode):
                continue
            nodes[_localname(str(s))] = _Node(_localname(str(s)), label_of(s), "rule", str(s), "M1")

        # M1 증상 (ext:Symptom 개체)
        for s in g.subjects(RDF.type, EXT.Symptom):
            if isinstance(s, BNode):
                continue
            lid = _localname(str(s))
            nodes[lid] = _Node(lid, label_of(s), "symptom", str(s), "M1")

        # M2 프로젝트 / 설계 / 요구 (kind=class 는 프로젝트 컨테이너를 뜻한다)
        for s in g.subjects(RDF.type, DOM_NS.Project):
            if isinstance(s, BNode) or not str(s).startswith(ENG):
                continue
            lid = _localname(str(s))
            nodes[lid] = _Node(lid, label_of(s), "class", str(s), "M2")
        for s in g.subjects(RDF.type, SPMM.RequiredBehavior):
            if isinstance(s, BNode) or not str(s).startswith(ENG):
                continue
            lid = _localname(str(s))
            nodes[lid] = _Node(lid, label_of(s), "requirement", str(s), "M2")
        for s in g.subjects(RDF.type, DOM_NS.WiperBlade):
            if isinstance(s, BNode) or not str(s).startswith(ENG):
                continue
            lid = _localname(str(s))
            nodes[lid] = _Node(lid, label_of(s), "design", str(s), "M2")

        # M0 상위 클래스 (spmm:/ext: 네임스페이스의 owl:Class)
        for s in g.subjects(RDF.type, OWL.Class):
            if isinstance(s, BNode):
                continue
            iri = str(s)
            if iri.startswith(str(SPMM)) or iri.startswith(str(EXT)):
                lid = _localname(iri)
                nodes.setdefault(lid, _Node(lid, label_of(s), "class", iri, "M0"))

        # M1 개념 (dom: 네임스페이스의 나머지 명명 노드 — 재질·차종·환경·거동·부품)
        for s in set(g.subjects(None, None)):
            if isinstance(s, BNode):
                continue
            iri = str(s)
            lid = _localname(iri)
            if lid in nodes or not iri.startswith(str(DOM)):
                continue
            # 스키마 술어(a owl:Class/Property 뿐)는 노드로 만들지 않는다 — 인스턴스·증상·개념만.
            types = set(g.objects(s, RDF.type))
            if not types:
                continue
            if OWL.ObjectProperty in types or OWL.DatatypeProperty in types or OWL.Ontology in types:
                continue
            nodes[lid] = _Node(lid, label_of(s), "concept", iri, "M1")

        return nodes

    # ── 엣지 유도 (+ 이행 폐포 추론 엣지) ──────────────────────────────────────
    def _edges(self, g: Graph, nodes: dict[str, _Node]) -> tuple[list[GraphEdge], set[tuple[str, str, str]]]:
        asserted: set[tuple[str, str, str]] = set()
        edges: list[GraphEdge] = []

        for s, p, o in g:
            if isinstance(s, BNode) or isinstance(o, (BNode, Literal)):
                continue
            pred = _EDGE_PREDICATES.get(str(p))
            if pred is None:
                continue
            sid, oid = _localname(str(s)), _localname(str(o))
            if sid not in nodes or oid not in nodes:
                continue
            key = (sid, pred, oid)
            if key in asserted:
                continue
            asserted.add(key)
            edges.append(GraphEdge(source=sid, target=oid, predicate=pred, inferred=False, evidence=None))

        inferred = self._inferred_edges(g, nodes, asserted)
        edges.extend(inferred)
        return edges, {(e.source, e.predicate, e.target) for e in inferred}

    def _inferred_edges(
        self, g: Graph, nodes: dict[str, _Node], asserted: set[tuple[str, str, str]]
    ) -> list[GraphEdge]:
        """owl:TransitiveProperty 의 이행 폐포 중 명시되지 않은 엣지를 추론 엣지로 만든다."""
        out: list[GraphEdge] = []
        for prop in g.subjects(RDF.type, OWL.TransitiveProperty):
            pred = _EDGE_PREDICATES.get(str(prop))
            if pred is None:
                continue
            adj: dict[str, set[str]] = {}
            for s, o in g.subject_objects(prop):
                if isinstance(s, BNode) or isinstance(o, (BNode, Literal)):
                    continue
                adj.setdefault(_localname(str(s)), set()).add(_localname(str(o)))
            # 이행 폐포 (BFS)
            for start in list(adj):
                seen: set[str] = set()
                stack = list(adj.get(start, set()))
                while stack:
                    cur = stack.pop()
                    if cur in seen:
                        continue
                    seen.add(cur)
                    stack.extend(adj.get(cur, set()))
                for reach in sorted(seen):
                    key = (start, pred, reach)
                    if key in asserted or start == reach:
                        continue
                    if start in nodes and reach in nodes:
                        out.append(GraphEdge(source=start, target=reach, predicate=pred, inferred=True, evidence=None))
        return out

    # ── 필터 지원 ──────────────────────────────────────────────────────────
    def _seed_ids(
        self, nodes: dict[str, _Node], symptom: str | None, sentence: str | None, project_id: str | None
    ) -> set[str] | None:
        if not any((symptom, sentence, project_id)):
            return None
        seeds: set[str] = set()
        if symptom and symptom in nodes:
            seeds.add(symptom)
        if sentence and sentence in nodes:
            seeds.add(sentence)
        if project_id:
            iri = self._project_iri(project_id)
            if iri:
                lid = _localname(iri)
                if lid in nodes:
                    seeds.add(lid)
        return seeds

    def _project_iri(self, project_id: str) -> str | None:
        esc = project_id.replace('"', '\\"')
        rows = self.store.query(
            f'SELECT ?p WHERE {{ ?p <{DOM}projectId> "{esc}" }}', readonly=False
        )
        return rows[0]["p"] if rows else None

    @staticmethod
    def _neighborhood(seeds: set[str], edges: list[GraphEdge], depth: int) -> set[str]:
        adj: dict[str, set[str]] = {}
        for e in edges:
            adj.setdefault(e.source, set()).add(e.target)
            adj.setdefault(e.target, set()).add(e.source)
        keep = set(seeds)
        frontier = set(seeds)
        for _ in range(max(0, depth)):
            nxt: set[str] = set()
            for n in frontier:
                nxt |= adj.get(n, set())
            nxt -= keep
            keep |= nxt
            frontier = nxt
        return keep
