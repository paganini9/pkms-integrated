"""CD-11 — 화이트리스트 명명 질의(`POST /kg/lookup`). Q&A A계층의 유일한 경로.

BFF 는 SPARQL 을 만들지 않는다(불변원칙 1). 대신 지식서비스가 **고정된** 질의 4종만 노출하고,
호출자는 `params` 로 IRI 바인딩만 넘긴다.

**주입 차단의 핵심**: `params` 는 rdflib `initBindings` 로 바인딩한다. SPARQL 문자열을 f-string 으로
보간하지 않는다. 예를 들어 `params={"vehicle": "> ?x } DELETE {"}` 는
`URIRef("http://ex.org/domain#> ?x } DELETE {")` 라는 **무해한(존재하지 않는) IRI** 로 바인딩되어
결과가 빈 배열이 될 뿐, 질의 구조를 바꾸지 못한다.

질의는 읽기 전용(SELECT)이며 rdflib Graph(스토어 스냅샷) 위에서 실행한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rdflib import Graph, Literal, URIRef

from schemas.errors import ValidationError
from schemas.models import Source
from store.oxigraph import DOM, OxigraphStore, _localname

# ── 화이트리스트 (이 밖의 query 는 422) ──────────────────────────────────────
NAMED_QUERIES = ("max_safe_length", "symptom_causes", "rule_sentences", "concept_relations")

_PREFIX = """
PREFIX dom: <http://ex.org/domain#>
PREFIX ext: <http://ex.org/spmm-ext#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

# 각 명명 질의가 요구하는 파라미터(=바인딩할 변수명). 전부 IRI(dom: 로컬네임)로 해석한다.
_REQUIRED_PARAMS = {
    "max_safe_length": ("vehicle",),
    "symptom_causes": ("symptom",),
    "rule_sentences": ("rule",),
    "concept_relations": ("concept",),
}

_Q_MAX = _PREFIX + """
SELECT ?vehicle ?max ?s ?text WHERE {
  ?vehicle dom:maxSafeLengthMm ?max .
  OPTIONAL {
    ?s a dom:KnowledgeSentence ; dom:mentions ?vehicle ;
       dom:aboutSymptom dom:TipChatter ; dom:sentenceText ?text .
  }
}
"""

_Q_SYMPTOM = _PREFIX + """
SELECT ?rule ?polarity ?basis WHERE {
  ?rule a dom:DesignRule ; dom:aboutSymptom ?symptom ;
        dom:polarity ?polarity ; dom:basis ?basis .
  FILTER(?polarity != "mitigate")
}
"""

_Q_RULE_SENTENCES = _PREFIX + """
SELECT ?s WHERE { ?rule dom:fromSentence ?s . }
"""

_Q_CONCEPT_RELATIONS = _PREFIX + """
SELECT ?s ?predicate ?o WHERE {
  { ?s ?predicate ?o . FILTER(?s = ?concept) }
  UNION
  { ?s ?predicate ?o . FILTER(?o = ?concept) }
  FILTER(?predicate IN (ext:causes, ext:mitigates, ext:aggravates, ext:conditionedOn))
}
"""


@dataclass(frozen=True)
class LookupResult:
    query: str
    rows: list[dict]
    sources: list[Source]


def _sentence_sort_key(code: str) -> tuple[int, str]:
    digits = "".join(ch for ch in code if ch.isdigit())
    return (int(digits) if digits else 1 << 30, code)


class KgLookup:
    """화이트리스트 명명 질의 실행기. 스토어 스냅샷(rdflib)을 매 호출 새로 만들어 결정론을 보장한다."""

    def __init__(self, store: OxigraphStore) -> None:
        self.store = store

    # ── 진입점 ────────────────────────────────────────────────────────────
    def lookup(self, query: str, params: dict[str, str] | None) -> LookupResult:
        if query not in NAMED_QUERIES:
            raise ValidationError(
                internal=f"named query '{query}' not in whitelist",
                user_message="지원하지 않는 조회입니다.",
                details={"field": "query", "allowed": list(NAMED_QUERIES)},
            )
        params = params or {}
        missing = [p for p in _REQUIRED_PARAMS[query] if not params.get(p)]
        if missing:
            raise ValidationError(
                internal=f"named query '{query}' missing params {missing}",
                user_message="조회에 필요한 값이 없습니다.",
                details={"field": "params", "required": missing},
            )

        graph = self.store.to_rdflib()
        handler: Callable[[Graph, dict[str, str]], LookupResult] = getattr(self, f"_{query}")
        return handler(graph, params)

    # ── IRI 바인딩(주입 차단의 유일한 지점) ─────────────────────────────────
    @staticmethod
    def _bind(params: dict[str, str], *names: str) -> dict[str, URIRef]:
        """params 값을 dom: 네임스페이스 IRI 로 바인딩한다. 문자열 보간이 아니라 initBindings 다."""
        return {n: URIRef(f"{DOM}{params[n]}") for n in names}

    # ── 각 명명 질의 ────────────────────────────────────────────────────────
    def _max_safe_length(self, graph: Graph, params: dict[str, str]) -> LookupResult:
        rows: list[dict] = []
        codes: set[str] = set()
        for r in graph.query(_Q_MAX, initBindings=self._bind(params, "vehicle")):
            code = _localname(str(r["s"])) if r["s"] is not None else None
            rows.append(
                {
                    "vehicle": _localname(str(r["vehicle"])),
                    "max_safe_mm": int(r["max"]),
                    "sentence": code,
                }
            )
            if code:
                codes.add(code)
        rows.sort(key=lambda x: str(x["vehicle"]))
        return LookupResult("max_safe_length", rows, self._sources_from_codes(graph, codes))

    def _symptom_causes(self, graph: Graph, params: dict[str, str]) -> LookupResult:
        rows: list[dict] = []
        codes: set[str] = set()
        for r in graph.query(_Q_SYMPTOM, initBindings=self._bind(params, "symptom")):
            basis = str(r["basis"])
            rows.append(
                {
                    "symptom": params["symptom"],
                    "rule": _localname(str(r["rule"])),
                    "polarity": str(r["polarity"]),
                    "sentence": basis,
                }
            )
            codes.update(c.strip() for c in basis.split(",") if c.strip())
        rows.sort(key=lambda x: str(x["rule"]))
        return LookupResult("symptom_causes", rows, self._sources_from_codes(graph, codes))

    def _rule_sentences(self, graph: Graph, params: dict[str, str]) -> LookupResult:
        rows: list[dict] = []
        codes: set[str] = set()
        for r in graph.query(_Q_RULE_SENTENCES, initBindings=self._bind(params, "rule")):
            code = _localname(str(r["s"]))
            rows.append({"rule": params["rule"], "sentence": code})
            codes.add(code)
        rows.sort(key=lambda x: _sentence_sort_key(str(x["sentence"])))
        return LookupResult("rule_sentences", rows, self._sources_from_codes(graph, codes))

    def _concept_relations(self, graph: Graph, params: dict[str, str]) -> LookupResult:
        rows: list[dict] = []
        for r in graph.query(_Q_CONCEPT_RELATIONS, initBindings=self._bind(params, "concept")):
            rows.append(
                {
                    "subject": _localname(str(r["s"])),
                    "predicate": _localname(str(r["predicate"])),
                    "object": _localname(str(r["o"])),
                }
            )
        rows.sort(key=lambda x: (str(x["subject"]), str(x["predicate"]), str(x["object"])))
        # 근거: 이 개념을 언급하는 문장들
        sources = self._sources_mentioning(graph, params["concept"])
        return LookupResult("concept_relations", rows, sources)

    # ── 근거(sources) 빌더 — 내부 구조(블랭크노드·트리플 원문) 비노출 ──────────
    def _sources_from_codes(self, graph: Graph, codes: set[str]) -> list[Source]:
        sources: list[Source] = []
        for code in sorted(codes, key=_sentence_sort_key):
            iri = f"{DOM}{code}"
            text = graph.value(URIRef(iri), URIRef(f"{DOM}sentenceText"))
            sources.append(Source(sentence=code, iri=iri, text=str(text) if text else None))
        return sources

    def _sources_mentioning(self, graph: Graph, concept: str) -> list[Source]:
        q = _PREFIX + """
        SELECT ?s ?text WHERE {
          ?s a dom:KnowledgeSentence ; dom:mentions ?concept ; dom:sentenceText ?text .
        }
        """
        found: dict[str, str] = {}
        for r in graph.query(q, initBindings={"concept": URIRef(f"{DOM}{concept}")}):
            found[_localname(str(r["s"]))] = str(r["text"])
        return [
            Source(sentence=code, iri=f"{DOM}{code}", text=found[code])
            for code in sorted(found, key=_sentence_sort_key)
        ]
