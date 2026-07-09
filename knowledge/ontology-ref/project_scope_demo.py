#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""프로젝트별 지식 적용 범위 데모.
'모든 지식이 모든 프로젝트에 적용되진 않는다' — 프로젝트가 선택한 지식 카테고리만 규칙/SHACL로 적용.
같은 설계 A(고무·600·8N·simple·SUV)라도 프로젝트의 지식 범위에 따라 검증 결과가 달라진다."""
from rdflib import Graph, RDF, RDFS, Namespace
from gen_shacl import compile_rules, validate, p

SH = Namespace("http://www.w3.org/ns/shacl#")
rules = Graph(); rules.parse(p("ontology/rules.ttl"), format="turtle")

projects = {
    "프로젝트 A (겨울용 SUV · 소음+떨림 지식 적용)": {"소음", "떨림"},
    "프로젝트 B (실내 진동시험 · 떨림 지식만 적용)": {"떨림"},
}
print("동일 설계 A(고무·600·8N·simple·SUV) — 프로젝트별 지식 범위 적용\n")
for name, cats in projects.items():
    gen, _, _ = compile_rules(rules, cats)
    ngate = len(list(gen.subjects(RDF.type, SH.NodeShape)))
    conforms, byfocus, full = validate(gen)
    print("=" * 64)
    print(f"{name}\n  적용 카테고리 {sorted(cats)} · 생성 게이트 {ngate}개 · conforms={conforms}")
    for f, msgs in byfocus.items():
        print(f"   · {full.value(f, RDFS.label)} — 위반 {len(msgs)}건: {', '.join(sorted(msgs))}")
    if not byfocus:
        print("   · 위반 없음")
