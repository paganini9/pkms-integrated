"""`/kg/save`·`/kg/delete` — 트리플 + 벡터 **원자성**.

저장 절차: (1) 트리플 커밋 → (2) 벡터 upsert. (2)가 실패하면 (1)을 보상 롤백하고 `StoreError`.
삭제도 동기(트리플·벡터). 벡터 실패 시 트리플을 되돌린다.

`derived`(rule·shapes·causal_edges)는 04 규칙 컴파일러 소관이라 `RuleCompiler` 주입을 우선 쓰고,
미완이면 rules.ttl(시드)에서 해당 문장의 규칙을 조회해 최소 형태로 채운다.
"""
from __future__ import annotations

from core.logging import get_trace_id
from schemas.errors import StoreError
from schemas.models import (
    Derived,
    DerivedRule,
    DerivedShape,
    DesignRuleCond,
    Relation,
    SaveRequest,
    SaveResponse,
    SavedSentence,
)
from store.oxigraph import DOM, OxigraphStore, _localname

# 극성 → 인과 술어(gen_shacl.py POL 과 동일)
_POL_PRED = {"cause": "causes", "aggravate": "aggravates", "mitigate": "mitigates"}
_PRED_POL = {"causes": "cause", "aggravates": "aggravate", "mitigates": "mitigate"}


class KgService:
    """트리플·벡터 원자성 저장/삭제."""

    def __init__(self, store: OxigraphStore, retriever=None, rule_compiler=None) -> None:  # noqa: ANN001
        self.store = store
        if retriever is None:
            from core.mocks import MockRetriever

            retriever = MockRetriever()
        self.retriever = retriever
        self.rule_compiler = rule_compiler  # 04 미완이면 None → rules.ttl 폴백

    # ── 저장 ────────────────────────────────────────────────────────────
    def save(self, req: SaveRequest) -> SaveResponse:
        # (0) 영속 멱등(T-83): 같은 draft_id 재요청은 **새로 저장하지 않고** 기존 결과를 돌려준다.
        # BFF in-memory 멱등은 재기동 시 소실되지만, draft_id 는 트리플에 남아 재기동·다중전송에도 중복 0.
        if req.draft_id:
            existing = self.store.sentence_by_draft_id(req.draft_id)
            if existing is not None:
                derived = self._build_derived(existing, req)
                return SaveResponse(
                    sentence=existing,
                    derived=derived,
                    human_view=self._human_view(derived),
                    trace_id=get_trace_id(),
                )

        mentions = self._resolve_mentions(req)
        about_symptom, polarity = self._infer_symptom_polarity(req)

        # (1) 트리플 커밋
        sentence: SavedSentence = self.store.save_sentence(
            req.sentence_text,
            req.category,
            mentions,
            about_symptom=about_symptom,
            polarity=polarity,
            draft_id=req.draft_id,
        )

        # (2) 벡터 upsert — 실패 시 (1) 보상 롤백
        try:
            self.retriever.upsert(
                [
                    {
                        "iri": sentence.iri,
                        "sentence": sentence.id,
                        "text": sentence.text,
                        "about_symptom": sentence.about_symptom,
                        "project_id": req.project_id,
                    }
                ]
            )
        except Exception as exc:  # noqa: BLE001 — 어떤 벡터 오류든 트리플을 되돌린다
            self.store.delete(sentence.iri)
            raise StoreError(internal=f"vector upsert failed, triples rolled back: {exc}") from exc

        derived = self._build_derived(sentence, req)
        human_view = self._human_view(derived)
        return SaveResponse(
            sentence=sentence,
            derived=derived,
            human_view=human_view,
            trace_id=get_trace_id(),
        )

    # ── 삭제 ────────────────────────────────────────────────────────────
    def delete(self, iris: list[str]) -> int:
        """트리플·벡터 동기 삭제. 벡터 실패 시 트리플 원상복구 후 StoreError."""
        removed_all: list = []
        try:
            for iri in iris:
                removed_all.extend(self.store.remove_about(iri))
            self.retriever.delete(list(iris))
        except Exception as exc:  # noqa: BLE001
            self.store.restore(removed_all)
            raise StoreError(internal=f"delete failed, triples restored: {exc}") from exc
        return len(iris)

    # ── mentions / symptom 해석 ─────────────────────────────────────────
    def _resolve_mentions(self, req: SaveRequest) -> list[str]:
        """개념 라벨 → 도메인 로컬네임(best-effort). 못 찾으면 라벨 그대로."""
        out: list[str] = []
        for c in req.concepts:
            out.append(self._label_to_localname(c.label) or c.label)
        return out

    def _label_to_localname(self, label: str) -> str | None:
        """rdfs:label 정확일치 → 부분일치 순으로 도메인 로컬네임을 찾는다.

        규칙/문장(DesignRule·KnowledgeSentence)은 개념이 아니므로 후보에서 제외한다
        (예: "고무" 가 NoiseRule 라벨 '겨울 + 고무 → 소음' 에 걸리는 오탐 방지).
        """
        esc = label.replace("\\", "\\\\").replace('"', '\\"')
        exclude = (
            f"FILTER NOT EXISTS {{ ?s a <{DOM}DesignRule> }} "
            f"FILTER NOT EXISTS {{ ?s a <{DOM}KnowledgeSentence> }}"
        )
        exact = self.store.query(
            f"SELECT ?s WHERE {{ ?s <http://www.w3.org/2000/01/rdf-schema#label> ?l "
            f'FILTER(str(?l) = "{esc}") {exclude} }}',
            readonly=False,
        )
        cand = exact or self.store.query(
            f"SELECT ?s WHERE {{ ?s <http://www.w3.org/2000/01/rdf-schema#label> ?l "
            f'FILTER(CONTAINS(str(?l), "{esc}")) {exclude} }}',
            readonly=False,
        )
        dom_iris = sorted(r["s"] for r in cand if r["s"].startswith(DOM))
        return _localname(dom_iris[0]) if dom_iris else None

    def _infer_symptom_polarity(self, req: SaveRequest) -> tuple[str | None, str]:
        """관계에서 about_symptom·polarity 를 유추한다."""
        for rel in req.relations:
            if rel.predicate in _PRED_POL:
                sym = self._label_to_localname(rel.object)
                return sym, _PRED_POL[rel.predicate]
        return None, "cause"

    # ── derived 구성 ────────────────────────────────────────────────────
    def _build_derived(self, sentence: SavedSentence, req: SaveRequest) -> Derived:
        if self.rule_compiler is not None:
            derived = self._derived_from_compiler(sentence, req)
            if derived is not None:
                return derived
        # 폴백: rules.ttl 에서 규칙 조회 → 최소 형태
        rule_iri = self._lookup_rule(sentence)
        if rule_iri is not None:
            return self._derived_from_rules_ttl(rule_iri, sentence)
        return self._derived_minimal(sentence, req)

    def _derived_from_compiler(self, sentence: SavedSentence, req: SaveRequest):  # noqa: ANN202
        """04 RuleCompiler 가 주입된 경우 위임. 실패/미지원 시 None 반환(폴백)."""
        try:
            self.rule_compiler.compile({sentence.category})
        except Exception:  # noqa: BLE001
            return None
        # 실제 CompiledRules→Derived 매핑은 04 확정 스키마에 의존 → 현재는 폴백에 위임
        return None

    def _lookup_rule(self, sentence: SavedSentence) -> str | None:
        """이 문장의 규칙 IRI 를 rules.ttl(시드)에서 찾는다.

        1) dom:fromSentence 가 이 문장을 가리키는 규칙, 2) 없으면 aboutSymptom 일치 규칙.
        """
        by_sentence = self.store.query(
            f"SELECT ?r WHERE {{ ?r a <{DOM}DesignRule> ; <{DOM}fromSentence> <{sentence.iri}> }}",
            readonly=False,
        )
        if by_sentence:
            return by_sentence[0]["r"]
        if sentence.about_symptom:
            # 같은 증상 + 같은 극성 규칙을 우선(예: Noise·cause → NoiseRule, mitigate 인 SiliconeRule 아님)
            by_sym_pol = self.store.query(
                f"SELECT ?r WHERE {{ ?r a <{DOM}DesignRule> ; "
                f"<{DOM}aboutSymptom> <{DOM}{sentence.about_symptom}> ; "
                f'<{DOM}polarity> "{sentence.polarity}" }}',
                readonly=False,
            )
            if by_sym_pol:
                return sorted(r["r"] for r in by_sym_pol)[0]
            by_sym = self.store.query(
                f"SELECT ?r WHERE {{ ?r a <{DOM}DesignRule> ; "
                f"<{DOM}aboutSymptom> <{DOM}{sentence.about_symptom}> }}",
                readonly=False,
            )
            if by_sym:
                return sorted(r["r"] for r in by_sym)[0]
        return None

    def _derived_from_rules_ttl(self, rule_iri: str, sentence: SavedSentence) -> Derived:
        meta = self.store.query(
            f"SELECT ?label ?pol ?cat ?basis ?sym WHERE {{ "
            f"<{rule_iri}> <http://www.w3.org/2000/01/rdf-schema#label> ?label ; "
            f"<{DOM}polarity> ?pol ; <{DOM}category> ?cat ; <{DOM}basis> ?basis ; "
            f"<{DOM}aboutSymptom> ?sym }}",
            readonly=False,
        )
        m = meta[0] if meta else {}
        label = m.get("label", sentence.text)
        polarity = m.get("pol", sentence.polarity)
        category = m.get("cat", sentence.category)
        basis = m.get("basis", sentence.id)
        symptom = _localname(m["sym"]) if m.get("sym") else (sentence.about_symptom or "")
        rule_id = _localname(rule_iri)

        conds = self._read_conds(rule_iri)
        rule = DerivedRule(
            id=rule_id,
            label=label,
            polarity=polarity,  # type: ignore[arg-type]
            category=category,
            about_symptom=symptom or None,
            basis=basis,
            conds=conds,
        )
        shapes: list[DerivedShape] = []
        if polarity in ("cause", "aggravate") and symptom:
            shapes.append(
                DerivedShape(id=rule_id.replace("Rule", "Shape"), gate_for=symptom, sentence=basis)
            )
        causal = [
            Relation(
                subject=rule_id,
                predicate=_POL_PRED.get(polarity, "causes"),  # type: ignore[arg-type]
                object=symptom or sentence.category,
                evidence=basis,
            )
        ]
        return Derived(rule=rule, shapes=shapes, causal_edges=causal)

    def _read_conds(self, rule_iri: str) -> list[DesignRuleCond]:
        rows = self.store.query(
            f"SELECT ?path ?op ?val WHERE {{ <{rule_iri}> <{DOM}hasCond> ?c . "
            f"?c <{DOM}onPath> ?path ; <{DOM}op> ?op . OPTIONAL {{ ?c <{DOM}val> ?val }} }}",
            readonly=False,
        )
        conds: list[DesignRuleCond] = []
        for r in rows:
            val = r.get("val")
            if val is not None and val.startswith(DOM):
                val = _localname(val)
            conds.append(
                DesignRuleCond(path=_localname(r["path"]), op=r["op"], val=val)  # type: ignore[arg-type]
            )
        return conds

    def _derived_minimal(self, sentence: SavedSentence, req: SaveRequest) -> Derived:
        """rules.ttl 에도 없는 신규 문장 — 요청과 문장에서 최소 규칙을 합성한다."""
        symptom = sentence.about_symptom or sentence.category
        polarity = sentence.polarity
        rule_id = f"{symptom}Rule"
        conds = [
            DesignRuleCond(
                path=rel.predicate,
                op="eq",
                val=(self._label_to_localname(rel.object) or rel.object),
            )
            for rel in req.relations
        ]
        rule = DerivedRule(
            id=rule_id,
            label=sentence.text,
            polarity=polarity,  # type: ignore[arg-type]
            category=sentence.category,
            about_symptom=sentence.about_symptom,
            basis=sentence.id,
            conds=conds,
        )
        shapes: list[DerivedShape] = []
        if polarity in ("cause", "aggravate"):
            shapes.append(
                DerivedShape(id=f"{symptom}Shape", gate_for=symptom, sentence=sentence.id)
            )
        causal = [
            Relation(
                subject=rule_id,
                predicate=_POL_PRED.get(polarity, "causes"),  # type: ignore[arg-type]
                object=symptom,
                evidence=sentence.id,
            )
        ]
        return Derived(rule=rule, shapes=shapes, causal_edges=causal)

    @staticmethod
    def _human_view(derived: Derived) -> list[str]:
        r = derived.rule
        sym = r.about_symptom or ""
        return [f"{r.label}  [{r.polarity}·{r.basis}·{r.category}] → {sym}"]
