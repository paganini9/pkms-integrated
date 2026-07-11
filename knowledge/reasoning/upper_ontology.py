"""CD-10 · FR-12 · AC-6 — 상위 온톨로지 조회·편집 게이트·영향 분석.

- `GET /upper-ontology/classes` : M0 클래스·관계 트리(m0.ttl 진실원).
- `POST /upper-ontology/classes`: HITL 게이트(불변원칙 4) — `approved:true` 없으면 409.
- `POST /upper-ontology/impact` : 상위 클래스 변경이 건드리는 **M1 문장·M2 인스턴스**를 반환.

일관성 검사는 신설하지 않는다 — 기존 `POST /reason/consistency` 를 쓴다(계약 §1.2).
"""
from __future__ import annotations

from pathlib import Path

from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace, URIRef
from rdflib.term import BNode

from core.config import settings
from core.logging import get_trace_id
from schemas.errors import GuardrailBlocked, ValidationError

DOM = Namespace("http://ex.org/domain#")
ENG = Namespace("http://ex.org/eng#")
SPMM = Namespace("http://ex.org/spmm#")
EXT = Namespace("http://ex.org/spmm-ext#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

_UPPER_NS = (str(SPMM), str(EXT))


def _local(u: object) -> str:
    s = str(u)
    return s.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _sentence_sort_key(code: str) -> tuple[int, str]:
    digits = "".join(ch for ch in code if ch.isdigit())
    return (int(digits) if digits else 1 << 30, code)


class UpperOntology:
    def __init__(self, ontology_dir: Path | None = None, overlay_path: Path | None = None) -> None:
        self._dir = ontology_dir or settings.ontology_dir
        # 승인 편집 오버레이(영속, 쓰기 가능). 시드 파일(읽기전용)과 분리한다 (T-85).
        self._overlay = overlay_path or settings.upper_overlay_path

    def _onto(self) -> Graph:
        g = Graph()
        for name in ("m0.ttl", "m1_wiper.ttl", "m2_instances.ttl"):
            g.parse(self._dir / name, format="turtle")
        self._merge_overlay(g)
        return g

    def _merge_overlay(self, g: Graph) -> None:
        """승인 편집 오버레이를 얹는다(존재 시). 재기동 후에도 이 파일이 있어 편집이 유지된다."""
        if self._overlay.exists():
            g.parse(self._overlay, format="turtle")

    def _load_overlay(self) -> Graph:
        ov = Graph()
        if self._overlay.exists():
            ov.parse(self._overlay, format="turtle")
        return ov

    def _save_overlay(self, ov: Graph) -> None:
        self._overlay.parent.mkdir(parents=True, exist_ok=True)
        ov.serialize(destination=self._overlay, format="turtle")

    # ── 조회 ────────────────────────────────────────────────────────────────
    def classes(self) -> dict:
        g = self._onto()
        upper: set[URIRef] = set()
        for c in g.subjects(RDF.type, OWL.Class):
            if isinstance(c, BNode):
                continue
            if str(c).startswith(_UPPER_NS):
                upper.add(c)
        # subClassOf 의 주어·목적어로 등장하는 클래스도 포함(일부는 a owl:Class 선언 없이
        # rdfs:subClassOf 로만 정의된다 — 예: ext:Symptom, ext:EnvCondition).
        for s, o in g.subject_objects(RDFS.subClassOf):
            for term in (s, o):
                if isinstance(term, URIRef) and str(term).startswith(_UPPER_NS):
                    upper.add(term)

        children: dict[str, list[str]] = {}
        parent_of: dict[str, str] = {}
        for c in upper:
            cid = _local(c)
            parents = [
                _local(o)
                for o in g.objects(c, RDFS.subClassOf)
                if isinstance(o, URIRef) and str(o).startswith(_UPPER_NS)
            ]
            parent_of[cid] = sorted(parents)[0] if parents else "owl:Thing"
            for p in parents:
                children.setdefault(_local(p), []).append(cid)

        classes = [
            {"id": cid, "parent": parent_of[cid], "children": sorted(children.get(cid, []))}
            for cid in sorted(parent_of)
        ]
        relations = []
        for p in sorted(g.subjects(RDF.type, OWL.ObjectProperty)):
            if isinstance(p, BNode) or not str(p).startswith(_UPPER_NS):
                continue
            dom = g.value(p, RDFS.domain)
            rng = g.value(p, RDFS.range)
            relations.append(
                {
                    "id": _local(p),
                    "domain": _local(dom) if dom else None,
                    "range": _local(rng) if rng else None,
                }
            )
        return {"classes": classes, "relations": relations, "trace_id": get_trace_id()}

    # ── 편집 게이트 (HITL) + 영속화 (T-85) ────────────────────────────────────
    def edit(self, changes: list[dict], approved: bool) -> dict:
        """HITL 게이트(미승인 409) 후, 승인 변경을 **오버레이 TTL 에 영속**한다.

        `{"op":"add","id":"Vibration","parent":"Symptom"}` → 상위 클래스 신설(부모 네임스페이스).
        재기동 후에도 오버레이가 남아 `classes()`·추론에 반영된다.
        """
        if not approved:
            raise GuardrailBlocked(internal="상위 온톨로지 변경 미승인 저장 시도")

        seed = self._onto()  # 부모 IRI 해석용(시드+기존 오버레이)
        overlay = self._load_overlay()
        applied = 0
        for ch in changes:
            op = str(ch.get("op", "add")).lower()
            cid = ch.get("id")
            if op != "add" or not cid:
                raise ValidationError(
                    f"지원하지 않는 변경: {ch!r} (op='add'·id 필수)", details={"field": "changes"}
                )
            parent = ch.get("parent")
            child_iri, parent_iri = self._resolve_new_class(seed, str(cid), parent)
            overlay.add((child_iri, RDF.type, OWL.Class))
            overlay.add((child_iri, RDFS.label, Literal(str(cid))))
            if parent_iri is not None:
                overlay.add((child_iri, RDFS.subClassOf, parent_iri))
            applied += 1

        self._save_overlay(overlay)
        return {"applied": applied, "persisted": True, "trace_id": get_trace_id()}

    # ── OOV 승인: altLabel 편입 (T-89 거버넌스·영속) ────────────────────────────
    def approve_altlabel(self, concept_iri: str, label: str, approved: bool) -> dict:
        """OOV 표기 이형을 승인해 개념의 skos:altLabel 로 **영속 편입**(오버레이 TTL).

        미승인이면 409. 편입 후엔 SpecValidator 가 오버레이를 읽어 그 라벨이 접지에 잡힌다
        (get_spec_validator 캐시는 라우트에서 무효화). 잘못된 개념 IRI 는 422.
        """
        if not approved:
            raise GuardrailBlocked(internal="altLabel 미승인 편입 시도")
        onto = self._onto()
        subj = URIRef(concept_iri if concept_iri.startswith("http") else f"{DOM}{concept_iri}")
        if (subj, None, None) not in onto:
            raise ValidationError(
                f"대상 개념을 찾을 수 없습니다: {concept_iri}", details={"field": "concept_iri"}
            )
        overlay = self._load_overlay()
        overlay.add((subj, SKOS.altLabel, Literal(label)))
        self._save_overlay(overlay)
        return {"approved": {"concept": _local(subj), "altLabel": label}, "persisted": True, "trace_id": get_trace_id()}

    def _resolve_new_class(
        self, g: Graph, cid: str, parent: str | None
    ) -> tuple[URIRef, URIRef | None]:
        """부모 로컬네임 → IRI 해석. 신규 클래스는 **부모와 같은 네임스페이스**에 만든다.

        부모 미지정/미해석이면 상위 확장 네임스페이스(ext:)에 owl:Class 로만 만든다.
        """
        parent_iri: URIRef | None = None
        if parent:
            for cand in g.subjects(RDF.type, OWL.Class):
                if isinstance(cand, URIRef) and _local(cand) == parent:
                    parent_iri = cand
                    break
            if parent_iri is None:  # subClassOf 로만 정의된 상위어(ext:Symptom 등)도 부모 후보
                for s, o in g.subject_objects(RDFS.subClassOf):
                    for term in (s, o):
                        if isinstance(term, URIRef) and _local(term) == parent:
                            parent_iri = term
                            break
                    if parent_iri is not None:
                        break
        ns = parent_iri.rsplit("#", 1)[0] + "#" if parent_iri else str(EXT)
        return URIRef(f"{ns}{cid}"), parent_iri

    # ── 영향 분석 (AC-6) ──────────────────────────────────────────────────────
    def impact(self, changes: list[dict]) -> dict:
        g = self._onto()
        targets = self._targets(changes)

        affected_iris: set[URIRef] = set()
        for t in targets:
            cls = URIRef(f"{DOM}{t}") if not t.startswith("http") else URIRef(t)
            # 상위 네임스페이스일 수도 있으니 두 후보 모두 시도
            for cand in {cls, URIRef(f"{SPMM}{t}"), URIRef(f"{EXT}{t}")}:
                affected_iris |= self._class_and_subclasses(g, cand)
        # 이 클래스(들)의 개체
        individuals: set[URIRef] = set()
        for c in list(affected_iris):
            for ind in g.subjects(RDF.type, c):
                if not isinstance(ind, BNode):
                    individuals.add(ind)
        affected_iris |= individuals

        affected_m1: set[str] = set()
        for s in g.subjects(RDF.type, DOM.KnowledgeSentence):
            refs = set(g.objects(s, DOM.mentions)) | set(g.objects(s, DOM.aboutSymptom)) | set(
                g.objects(s, DOM.derivesRule)
            )
            if refs & affected_iris:
                affected_m1.add(_local(s))

        affected_m2: set[str] = set()
        for ind in individuals | set(self._eng_instances(g)):
            if not str(ind).startswith(str(ENG)):
                continue
            if ind in affected_iris or (set(g.objects(ind, None)) & affected_iris):
                affected_m2.add(_local(ind))

        return {
            "affected_m1": sorted(affected_m1, key=_sentence_sort_key),
            "affected_m2": sorted(affected_m2),
            "trace_id": get_trace_id(),
        }

    @staticmethod
    def _targets(changes: list[dict]) -> set[str]:
        keys = ("id", "target", "class", "subject", "cls")
        out: set[str] = set()
        for ch in changes:
            if isinstance(ch, str):
                out.add(ch)
                continue
            for k in keys:
                v = ch.get(k)
                if isinstance(v, str) and v:
                    out.add(_local(v))
                    break
        return out

    @staticmethod
    def _class_and_subclasses(g: Graph, cls: URIRef) -> set[URIRef]:
        result = {cls}
        frontier = {cls}
        while frontier:
            nxt: set[URIRef] = set()
            for c in frontier:
                for sub in g.subjects(RDFS.subClassOf, c):
                    if isinstance(sub, URIRef) and sub not in result:
                        result.add(sub)
                        nxt.add(sub)
            frontier = nxt
        return result

    @staticmethod
    def _eng_instances(g: Graph) -> set[URIRef]:
        return {s for s in g.subjects(RDF.type, None) if not isinstance(s, BNode) and str(s).startswith(str(ENG))}
