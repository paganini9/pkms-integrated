"""문장 원천 추상화 — 검색 인덱스에 넣을 지식문장의 공급자.

06 퍼시스턴스(Store)가 미완이므로 **TTL 직독 구현**(`TtlSentenceSource`)으로 선행한다.
G1 에서 Store 기반 구현으로 교체 가능하도록 `SentenceSource` Protocol 로 추상화한다.

CD-3: 규칙 식별자의 단일 진실원은 `rules.ttl`(NoiseRule·SiliconeRule·ChatterRule·SpringRule·ArmRule).
`m1_wiper.ttl` 의 `derivesRule`(AggravationRule 등)은 무시하고, `rules.ttl` 의 `fromSentence`
역참조를 정방향 진실원으로 삼는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from rdflib import Graph, Namespace, RDF, URIRef

from core.config import settings

DOM = Namespace("http://ex.org/domain#")


@dataclass(frozen=True)
class SentenceRecord:
    """검색 대상 지식문장 한 건."""

    iri: str
    code: str  # 로컬네임 (S1..S6) — CD-2 문장 코드
    text: str
    category: str | None
    about_symptom: str | None  # 증상 로컬네임 (Noise, TipChatter)
    derives_rule: str | None  # 대표 규칙 1개 (rules.ttl 기준)
    derives_rules: list[str] = field(default_factory=list)  # 걸린 규칙 전체
    polarity: str | None = None  # cause | mitigate | aggravate


@dataclass(frozen=True)
class CategoryStat:
    name: str
    sentences: int
    rules: int


@runtime_checkable
class SentenceSource(Protocol):
    def sentences(self) -> list[SentenceRecord]: ...
    def categories(self) -> list[CategoryStat]: ...


def _local(uri: URIRef | str) -> str:
    s = str(uri)
    return s.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


class TtlSentenceSource:
    """`settings.ontology_dir` 의 `m1_wiper.ttl`·`rules.ttl` 을 rdflib 로 파싱한다."""

    def __init__(self, ontology_dir: Path | None = None) -> None:
        self.ontology_dir = Path(ontology_dir or settings.ontology_dir)
        self._m1: Graph | None = None
        self._rules: Graph | None = None

    # ── 그래프 로드(지연) ────────────────────────────────────────────────
    def _load(self) -> tuple[Graph, Graph]:
        if self._m1 is None or self._rules is None:
            m1 = Graph()
            m1.parse(self.ontology_dir / "m1_wiper.ttl", format="turtle")
            rules = Graph()
            rules.parse(self.ontology_dir / "rules.ttl", format="turtle")
            self._m1, self._rules = m1, rules
        return self._m1, self._rules

    # ── rules.ttl 역참조: 문장 로컬네임 → 걸린 규칙(로컬네임) 리스트 ──────
    def _rule_map(self, rules: Graph) -> dict[str, list[str]]:
        """fromSentence 를 정방향 진실원으로: sentence_code → [rule_code...] (정렬)."""
        mapping: dict[str, list[str]] = {}
        for rule, _, sent in rules.triples((None, DOM.fromSentence, None)):
            mapping.setdefault(_local(sent), []).append(_local(rule))
        for code in mapping:
            mapping[code] = sorted(set(mapping[code]))
        return mapping

    def _rule_category(self, rules: Graph) -> dict[str, str]:
        out: dict[str, str] = {}
        for rule, _, cat in rules.triples((None, DOM.category, None)):
            out[_local(rule)] = str(cat)
        return out

    # ── 공개 API ─────────────────────────────────────────────────────────
    def sentences(self) -> list[SentenceRecord]:
        m1, rules = self._load()
        rule_map = self._rule_map(rules)
        rule_cat = self._rule_category(rules)

        records: list[SentenceRecord] = []
        for s in m1.subjects(RDF.type, DOM.KnowledgeSentence):
            code = _local(s)
            text_val = m1.value(s, DOM.sentenceText)
            if text_val is None:
                continue
            about = m1.value(s, DOM.aboutSymptom)
            polarity = m1.value(s, DOM.polarity)

            derived = rule_map.get(code, [])
            rep = derived[0] if derived else None
            # 카테고리는 대표 규칙(rules.ttl)의 dom:category 로 매핑
            category = rule_cat.get(rep) if rep else None

            records.append(
                SentenceRecord(
                    iri=str(s),
                    code=code,
                    text=str(text_val),
                    category=category,
                    about_symptom=_local(about) if about else None,
                    derives_rule=rep,
                    derives_rules=derived,
                    polarity=str(polarity) if polarity else None,
                )
            )
        records.sort(key=lambda r: r.code)
        return records

    def categories(self) -> list[CategoryStat]:
        _, rules = self._load()
        rule_cat = self._rule_category(rules)

        # 카테고리별 규칙 수
        rules_by_cat: dict[str, set[str]] = {}
        for rule_code, cat in rule_cat.items():
            rules_by_cat.setdefault(cat, set()).add(rule_code)

        # 카테고리별 문장 수 — 규칙의 fromSentence 를 카테고리로 접어 계수
        sents_by_cat: dict[str, set[str]] = {}
        for rule, _, sent in rules.triples((None, DOM.fromSentence, None)):
            cat = rule_cat.get(_local(rule))
            if cat is None:
                continue
            sents_by_cat.setdefault(cat, set()).add(_local(sent))

        cats = sorted(set(rules_by_cat) | set(sents_by_cat))
        return [
            CategoryStat(
                name=c,
                sentences=len(sents_by_cat.get(c, set())),
                rules=len(rules_by_cat.get(c, set())),
            )
            for c in cats
        ]

    def known_rules(self) -> dict[str, str]:
        """rule_code → category (검증기 시드용)."""
        _, rules = self._load()
        return self._rule_category(rules)
