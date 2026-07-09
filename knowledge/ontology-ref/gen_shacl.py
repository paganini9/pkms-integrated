#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""단일 진실원 데모 — 구조화 DesignRule(rules.ttl) → SHACL·인과엣지·사람뷰 파생.
compile_rules(rules, categories) 로 프로젝트별 지식범위 필터 지원(project_scope_demo.py 재사용)."""
import os
from rdflib import Graph, Namespace, RDF, RDFS, URIRef, Literal, BNode
from rdflib.collection import Collection
import pyshacl

DOM = Namespace("http://ex.org/domain#"); EXT = Namespace("http://ex.org/spmm-ext#")
SH  = Namespace("http://www.w3.org/ns/shacl#")
HERE = os.path.dirname(os.path.abspath(__file__))
def p(x): return os.path.join(HERE, x)
def iri(u): return f"<{u}>"
def loc(u): return str(u).split('#')[-1]
POL = {"cause":"causes", "mitigate":"mitigates", "aggravate":"aggravates"}

def cond_to_sparql(rules, cond):
    path = rules.value(cond, DOM.onPath); op = str(rules.value(cond, DOM.op)); val = rules.value(cond, DOM.val)
    if op == "eq":
        if isinstance(val, URIRef): return f"$this {iri(path)} {iri(val)} ."
        return f'$this {iri(path)} ?{loc(path)} . FILTER(str(?{loc(path)}) = "{val}")'
    if op in ("lt","le","gt","ge"):
        s = {"lt":"<","le":"<=","gt":">","ge":">="}[op]
        return f"$this {iri(path)} ?{loc(path)} . FILTER(?{loc(path)} {s} {val})"
    if op == "gtPath":
        p1, p2 = list(Collection(rules, rules.value(cond, DOM.refList)))
        return f"$this {iri(path)} ?a . $this {iri(p1)} ?x . ?x {iri(p2)} ?b . FILTER(?a > ?b)"
    return ""

def compile_rules(rules, categories=None):
    """rules → (shapes, causal, human). categories=None 이면 전체, 아니면 해당 카테고리 규칙만."""
    gen = Graph(); gen.bind("sh", SH); gen.bind("dom", DOM); causal = Graph(); human = []
    for rule in sorted(rules.subjects(RDF.type, DOM.DesignRule)):
        cat = str(rules.value(rule, DOM.category)) if rules.value(rule, DOM.category) else None
        if categories is not None and cat not in categories:
            continue
        label = str(rules.value(rule, RDFS.label)); symptom = rules.value(rule, DOM.aboutSymptom)
        pol = str(rules.value(rule, DOM.polarity)); basis = str(rules.value(rule, DOM.basis))
        conds = list(rules.objects(rule, DOM.hasCond))
        human.append(f"{label}  [{pol}·{basis}·{cat}] → {loc(symptom)}")
        causal.add((rule, EXT[POL[pol]], symptom))
        if pol in ("cause", "aggravate"):
            shape = DOM[loc(rule).replace("Rule", "Shape")]; where = " ".join(cond_to_sparql(rules, c) for c in conds)
            gen.add((shape, RDF.type, SH.NodeShape)); gen.add((shape, SH.targetClass, DOM.WiperBlade))
            gen.add((shape, DOM.gateFor, symptom)); gen.add((shape, DOM.sentence, Literal(basis)))
            sp = BNode(); gen.add((shape, SH.sparql, sp)); gen.add((sp, SH.severity, SH.Violation))
            gen.add((sp, SH.message, Literal(f"[{basis}] {label}")))
            gen.add((sp, SH.select, Literal(f"SELECT $this WHERE {{ {where} }}")))
    return gen, causal, human

def validate(shapes):
    onto = Graph(); onto.parse(p("ontology/m0.ttl")); onto.parse(p("ontology/m1_wiper.ttl"))
    data = Graph(); data.parse(p("ontology/m2_instances.ttl")); full = onto + data
    conforms, rg, _ = pyshacl.validate(full, shacl_graph=shapes, ont_graph=None, inference="none", advanced=True)
    byfocus = {}
    for r in rg.subjects(RDF.type, SH.ValidationResult):
        byfocus.setdefault(rg.value(r, SH.focusNode), []).append(str(rg.value(r, SH.resultMessage)))
    return conforms, byfocus, full

if __name__ == "__main__":
    rules = Graph(); rules.parse(p("ontology/rules.ttl"), format="turtle")
    gen, causal, human = compile_rules(rules)
    gen.serialize(p("ontology/shapes_generated.ttl"), format="turtle")
    print("규칙 소스: rules.ttl → 파생\n" + "="*64)
    print("(a) SHACL 게이트:", len(list(gen.subjects(RDF.type, SH.NodeShape))), "개 → shapes_generated.ttl")
    for s in sorted(gen.subjects(RDF.type, SH.NodeShape)):
        print(f"     {loc(s)}  gateFor={loc(gen.value(s, DOM.gateFor))}  basis={gen.value(s, DOM.sentence)}")
    print("(b) 인과 엣지:"); [print(f"     {loc(s)} {loc(pr)} {loc(o)}") for s, pr, o in sorted(causal)]
    print("(c) 사람용 뷰:"); [print("   ·", h) for h in human]
    conforms, byfocus, full = validate(gen)
    print("\n생성 SHACL 검증: conforms =", conforms)
    for f, msgs in byfocus.items():
        print(f"   · {full.value(f, RDFS.label)} — 위반 {len(msgs)}건"); [print("      ", m) for m in sorted(msgs)]
