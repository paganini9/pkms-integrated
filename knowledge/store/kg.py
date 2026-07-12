"""`/kg/save`·`/kg/delete` — 트리플 + 벡터 **원자성**.

저장 절차: (1) 트리플 커밋 → (2) 벡터 upsert. (2)가 실패하면 (1)을 보상 롤백하고 `StoreError`.
삭제도 동기(트리플·벡터). 벡터 실패 시 트리플을 되돌린다.

`derived`(rule·shapes·causal_edges)는 04 규칙 컴파일러 소관이라 `RuleCompiler` 주입을 우선 쓰고,
미완이면 rules.ttl(시드)에서 해당 문장의 규칙을 조회해 최소 형태로 채운다.
"""
from __future__ import annotations

from rdflib import Namespace as _RdflibNamespace
from rdflib import URIRef as RDFLIB_URIREF

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
from store.naming import slug_localname
from store.oxigraph import DOM, OxigraphStore, _localname

# 극성 → 인과 술어(gen_shacl.py POL 과 동일)
_POL_PRED = {"cause": "causes", "aggravate": "aggravates", "mitigate": "mitigates"}
_PRED_POL = {"causes": "cause", "aggravates": "aggravate", "mitigates": "mitigate"}

RDFLIB_DOM = _RdflibNamespace(DOM)


class KgService:
    """트리플·벡터 원자성 저장/삭제."""

    def __init__(  # noqa: ANN001
        self, store: OxigraphStore, retriever=None, rule_compiler=None, authoring_store=None, reifier=None
    ) -> None:
        self.store = store
        if retriever is None:
            from core.mocks import MockRetriever

            retriever = MockRetriever()
        self.retriever = retriever
        self.rule_compiler = rule_compiler  # 04 미완이면 None → rules.ttl 폴백
        # T-93 — 저작 파생 규칙 오버레이 + Causation reify. 주입 안 되면 기본(캐시된) 구현을 쓴다.
        # reifier 는 온톨로지를 파싱하므로 요청마다 새로 만들지 않는다(get_reifier = lru_cache).
        from reasoning.authoring import AuthoringRuleStore
        from reasoning.causation import get_reifier

        self.authoring_store = authoring_store or AuthoringRuleStore()
        self.reifier = reifier or get_reifier()

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

        mentions, mention_labels = self._resolve_mentions(req)
        about_symptom, polarity = self._infer_symptom_polarity(req)

        # (1) 트리플 커밋
        sentence: SavedSentence = self.store.save_sentence(
            req.sentence_text,
            req.category,
            mentions,
            about_symptom=about_symptom,
            polarity=polarity,
            draft_id=req.draft_id,
            mention_labels=mention_labels,
        )

        # (2) 저작 파생 — 규칙(오버레이 영속) + Causation reify(저장 그래프 기록). T-93.
        rule = self._derive_and_persist_rule(sentence, req)
        causation_iris = self._persist_causation(sentence, req)

        # (3) 벡터 upsert — 실패 시 (1)(2) 전부 보상 롤백
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
            for iri in causation_iris:
                self.store.remove_about(iri)
            if rule is not None:
                self.authoring_store.remove(rule.id)
            raise StoreError(internal=f"vector upsert failed, triples rolled back: {exc}") from exc

        derived = self._build_derived(sentence, req, rule)
        human_view = self._human_view(derived)
        return SaveResponse(
            sentence=sentence,
            derived=derived,
            human_view=human_view,
            trace_id=get_trace_id(),
        )

    # ── T-93: 저작 파생 (규칙 · Causation) ──────────────────────────────
    def _derive_and_persist_rule(self, sentence: SavedSentence, req: SaveRequest):  # noqa: ANN202
        """승인 문장 → 구조화 규칙 → **오버레이 영속**. 컴파일러가 다음 판정부터 이 규칙을 소비한다.

        이미 등가 규칙(시드든 저작이든)이 있으면 새로 만들지 않는다 — 같은 사실을 다시 말한 것뿐이다.
        (안 그러면 게이트가 둘로 늘어 같은 위반이 두 번 잡히고, 시드 등가 문장이 시드 회귀를 깬다.)
        """
        from reasoning.authoring import derive_rule, find_equivalent

        rule = derive_rule(
            sentence_code=sentence.id,
            sentence_text=sentence.text,
            category=sentence.category,
            concepts=req.concepts,
            relations=req.relations,
            validator=self.reifier.validator,
        )
        if rule is None:
            return None
        existing = find_equivalent(rule, self._existing_rules())
        if existing is not None:
            return existing  # 새 규칙 없음 — 기존 규칙이 이 문장의 derived 다
        self.authoring_store.upsert(rule)
        return rule

    def _existing_rules(self) -> list:
        """현재 컴파일 대상 규칙 전체(시드 + 저작 오버레이)."""
        if self.rule_compiler is not None:
            return list(self.rule_compiler.rules)
        from core.config import settings
        from reasoning.rules import load_rules

        return [*load_rules(settings.ontology_dir / "rules.ttl"), *self.authoring_store.rules()]

    def _persist_causation(self, sentence: SavedSentence, req: SaveRequest) -> list[str]:
        """T-91 배선 — 인과 프레임을 Causation 노드로 재화해 **저장 그래프에 실제로 기록**한다.

        예전엔 reifier 가 유닛 테스트에서만 불렸다(저장 그래프의 Causation 0행). 이제 저작이 만든
        (기전·조건·증상) 바인딩이 그래프에 남는다.
        """
        nodes = self.reifier.reify(req.concepts, req.relations, sentence_code=sentence.id)
        if not nodes:
            return []
        graph = self.reifier.to_graph(nodes)
        for node in nodes:
            graph.add((node.iri, RDFLIB_DOM.fromSentence, RDFLIB_URIREF(sentence.iri)))
        self.store.add_rdflib_graph(graph)
        return [str(n.iri) for n in nodes]

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
    def _resolve_mentions(self, req: SaveRequest) -> tuple[list[str], dict[str, str]]:
        """개념 라벨 → (로컬네임 목록, 새 개념의 표면형 라벨).

        T-92: 어휘층에서 해석되면 시드 로컬네임(WiperBlade)을 쓰고, 아니면 **라벨을 슬러그화**한다.
        예전엔 라벨을 그대로 IRI 에 이어붙여 공백 하나에 저장이 500 으로 죽었다.
        새로 발행한 개념의 표면형은 `rdfs:label` 로 보존한다(라벨→IRI 는 단방향 손실이므로).
        """
        out: list[str] = []
        labels: dict[str, str] = {}
        for c in req.concepts:
            # 어휘층(prefLabel + 승인된 altLabel) 이 1순위다 — 스토어 라벨 조회는 altLabel 을 모른다.
            # (안 그러면 "오존 노출"(altLabel of Ozone)이 mentions 에선 새 IRI 로 발행돼 그래프가 어긋난다.)
            known = self._iri_localname(c.label) or self._label_to_localname(c.label)
            if known:
                out.append(known)
                continue
            minted = slug_localname(c.label)
            out.append(minted)
            labels[minted] = c.label
        return out, labels

    def _iri_localname(self, label: str) -> str | None:
        iri = self.reifier.validator.iri_for(label)
        return _localname(iri) if iri else None

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
                # T-92 — 미해석 증상도 슬러그로 심는다(라벨 그대로면 IRI 가 깨진다).
                sym = self._label_to_localname(rel.object) or slug_localname(rel.object)
                return sym, _PRED_POL[rel.predicate]
        return None, "cause"

    # ── derived 구성 ────────────────────────────────────────────────────
    def _build_derived(self, sentence: SavedSentence, req: SaveRequest, rule=None) -> Derived:  # noqa: ANN001
        # T-93 — 저작이 실제로 파생·영속한 규칙이 있으면 **그것**이 derived 다.
        # (예전엔 카테고리명 규칙(소음Rule)을 지어내 증상을 카테고리로 오귀속했다.)
        if rule is not None:
            return self._derived_from_rule(rule, sentence)
        # 시드 문장(S1~S6) 재저장 등: rules.ttl 의 규칙 조회 → 최소 형태
        rule_iri = self._lookup_rule(sentence)
        if rule_iri is not None:
            return self._derived_from_rules_ttl(rule_iri, sentence)
        return self._derived_minimal(sentence, req)

    def _derived_from_rule(self, rule, sentence: SavedSentence) -> Derived:  # noqa: ANN001
        """파생 RuleSpec → 계약 형태(Derived). 게이트·인과엣지는 규칙이 말하는 그대로."""
        return Derived(
            rule=DerivedRule(
                id=rule.id,
                label=rule.label,
                polarity=rule.polarity,
                category=rule.category,
                about_symptom=rule.symptom,
                basis=rule.basis,
                conds=[
                    DesignRuleCond(path=c.path, op=c.op, val=_localname(str(c.val)) if c.val is not None else None)
                    for c in rule.conds
                ],
            ),
            shapes=[DerivedShape(id=rule.shape_id, gate_for=rule.symptom, sentence=rule.basis)]
            if rule.makes_gate
            else [],
            causal_edges=[
                Relation(
                    subject=rule.id,
                    predicate=_POL_PRED[rule.polarity],  # type: ignore[arg-type]
                    object=rule.symptom,
                    evidence=rule.basis,
                )
            ],
        )

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
