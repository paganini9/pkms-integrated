"""구조화 DesignRule 로딩 — 단일 진실원은 `ontology/rules.ttl` (CD-3).

엔지니어는 자연어 문장을 편집하고, 규칙·SHACL 은 여기서 파생된다.
문장의 극성(polarity)은 `m1_wiper.ttl` 의 `dom:polarity` 를 쓴다 — CD-1 정규화의 근거다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection

DOM = Namespace("http://ex.org/domain#")

GATE_POLARITIES = frozenset({"cause", "aggravate"})
"""게이트(SHACL NodeShape)를 만드는 극성. `mitigate` 는 원인의 여집합이라 게이트가 없다."""


def loc(u: object) -> str:
    return str(u).split("#")[-1]


@dataclass(frozen=True)
class Cond:
    path: str
    op: str
    val: URIRef | Literal | None = None
    ref_list: tuple[str, ...] = ()

    @property
    def is_numeric(self) -> bool:
        return self.op in {"lt", "le", "gt", "ge", "gtPath"}


@dataclass(frozen=True)
class RuleSpec:
    id: str
    label: str
    category: str
    polarity: str
    basis: str
    symptom: str
    conds: tuple[Cond, ...] = ()
    from_sentences: tuple[str, ...] = ()

    @property
    def makes_gate(self) -> bool:
        return self.polarity in GATE_POLARITIES

    @property
    def shape_id(self) -> str:
        """NoiseRule → NoiseShape."""
        return self.id.replace("Rule", "Shape")

    @property
    def basis_sentences(self) -> tuple[str, ...]:
        return tuple(s.strip() for s in self.basis.split(",") if s.strip())


def load_rules(rules_ttl: Path) -> list[RuleSpec]:
    g = Graph().parse(rules_ttl, format="turtle")
    specs: list[RuleSpec] = []

    for rule in sorted(g.subjects(RDF.type, DOM.DesignRule)):
        conds: list[Cond] = []
        for c in g.objects(rule, DOM.hasCond):
            path = loc(g.value(c, DOM.onPath))
            op = str(g.value(c, DOM.op))
            ref = g.value(c, DOM.refList)
            ref_list = tuple(loc(x) for x in Collection(g, ref)) if ref is not None else ()
            conds.append(Cond(path=path, op=op, val=g.value(c, DOM.val), ref_list=ref_list))

        specs.append(
            RuleSpec(
                id=loc(rule),
                label=str(g.value(rule, RDFS.label)),
                category=str(g.value(rule, DOM.category)),
                polarity=str(g.value(rule, DOM.polarity)),
                basis=str(g.value(rule, DOM.basis)),
                symptom=loc(g.value(rule, DOM.aboutSymptom)),
                conds=tuple(conds),
                from_sentences=tuple(sorted(loc(s) for s in g.objects(rule, DOM.fromSentence))),
            )
        )
    return specs


def load_sentence_polarity(m1_ttl: Path) -> dict[str, str]:
    """문장 코드 → 극성. CD-1: `violations` 는 cause·aggravate 문장만 남긴다.

    S5("소형 세단은 550mm까지 문제 없다")는 mitigate 라 위반 목록에서 빠진다.
    이것이 AC-2(S1·S3·S4·S6)와 회귀셋 scope-A(["S1","S3,S5",…])를 동시에 성립시키는 해석이다.
    """
    g = Graph().parse(m1_ttl, format="turtle")
    return {
        loc(s): str(g.value(s, DOM.polarity))
        for s in g.subjects(RDF.type, DOM.KnowledgeSentence)
        if g.value(s, DOM.polarity) is not None
    }


def sentence_sort_key(code: str) -> tuple[int, str]:
    """S2 < S10 이 되도록 숫자 접미사로 정렬한다(문자열 정렬이면 S10 < S2)."""
    digits = "".join(ch for ch in code if ch.isdigit())
    return (int(digits) if digits else 1 << 30, code)


def normalize_violations(bases: list[str], sentence_polarity: dict[str, str]) -> list[str]:
    """CD-1 — basis 를 콤마 분해 → 극성 cause·aggravate 만 → 정렬·중복제거.

    >>> normalize_violations(["S1", "S3,S5", "S4", "S6"], {"S1":"cause","S3":"cause","S5":"mitigate","S4":"cause","S6":"cause"})
    ['S1', 'S3', 'S4', 'S6']
    """
    out: set[str] = set()
    for base in bases:
        for code in (c.strip() for c in base.split(",")):
            if not code:
                continue
            # 극성을 모르는 문장은 보수적으로 포함한다(누락보다 과다표시가 안전).
            if sentence_polarity.get(code, "cause") in GATE_POLARITIES:
                out.add(code)
    return sorted(out, key=sentence_sort_key)
