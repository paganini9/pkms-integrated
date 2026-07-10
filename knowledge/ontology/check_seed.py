#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시드 TTL 일관성 점검 (02 데이터 Agent 소유) — T-11.

계약(CD-3)이 깨지면 여기서 먼저 실패해야 한다. CI(T-82)에서 호출한다.

    knowledge/.venv/Scripts/python.exe knowledge/ontology/check_seed.py [ttl_dir]

`ttl_dir` 생략 시 이 스크립트가 있는 디렉터리. (정규화 전 원본을 검사해 검증기가 살아있는지 확인할 때 유용)

점검 항목
  1. 6문장(S1~S6) 존재 · sentenceText·polarity·aboutSymptom 채워짐
  2. 규칙의 단일 진실원은 rules.ttl — m1_wiper.ttl 이 DesignRule 을 재선언하지 않는다 (CD-3)
  3. 문장→규칙(derivesRule)이 rules.ttl 의 규칙만 가리킨다 (AggravationRule 잔재 금지)
  4. 규칙→문장(fromSentence)이 실재 문장만 가리키고, basis 와 일치한다
  5. 카테고리는 {소음, 떨림}. 게이트(cause·aggravate) 수 = 카테고리별 AC-scope 기대치
  6. 극성은 cause·mitigate·aggravate 중 하나
"""
import sys
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Namespace, URIRef

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOM = Namespace("http://ex.org/domain#")
OWL_CLASS = URIRef("http://www.w3.org/2002/07/owl#Class")
HERE = Path(__file__).resolve().parent

EXPECTED_SENTENCES = {"S1", "S2", "S3", "S4", "S5", "S6"}
EXPECTED_RULES = {"NoiseRule", "SiliconeRule", "ChatterRule", "SpringRule", "ArmRule"}
EXPECTED_CATEGORIES = {"소음", "떨림"}
# AC-scope: 프로젝트 A(소음+떨림)=4게이트 / B(떨림)=3게이트. 게이트는 cause·aggravate 만.
EXPECTED_GATES = {frozenset({"소음", "떨림"}): 4, frozenset({"떨림"}): 3}
GATE_POLARITIES = {"cause", "aggravate"}


def loc(u) -> str:
    return str(u).split("#")[-1]


def main() -> int:
    ttl_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    m1 = Graph().parse(ttl_dir / "m1_wiper.ttl", format="turtle")
    rules = Graph().parse(ttl_dir / "rules.ttl", format="turtle")
    errors: list[str] = []

    # 1. 6문장
    sentences = {loc(s) for s in m1.subjects(RDF.type, DOM.KnowledgeSentence)}
    if sentences != EXPECTED_SENTENCES:
        errors.append(f"문장 집합 불일치: {sorted(sentences)} != {sorted(EXPECTED_SENTENCES)}")
    for s in m1.subjects(RDF.type, DOM.KnowledgeSentence):
        for prop, name in ((DOM.sentenceText, "sentenceText"), (DOM.polarity, "polarity"), (DOM.aboutSymptom, "aboutSymptom")):
            if m1.value(s, prop) is None:
                errors.append(f"{loc(s)}: {name} 누락")

    # 2. rules.ttl 이 단일 진실원 — m1 에 DesignRule 인스턴스 재선언 금지 (owl:Class 선언은 허용)
    m1_rule_decls = {loc(s) for s in m1.subjects(RDF.type, DOM.DesignRule)}
    if m1_rule_decls:
        errors.append(f"CD-3 위반: m1_wiper.ttl 이 DesignRule 을 재선언함 {sorted(m1_rule_decls)} — rules.ttl 이 진실원")

    rule_names = {loc(r) for r in rules.subjects(RDF.type, DOM.DesignRule)}
    if rule_names != EXPECTED_RULES:
        errors.append(f"규칙 집합 불일치: {sorted(rule_names)} != {sorted(EXPECTED_RULES)}")

    # 3. 문장 → 규칙 참조가 rules.ttl 안에만 있는가
    for s, _, r in m1.triples((None, DOM.derivesRule, None)):
        if loc(r) not in rule_names:
            errors.append(f"{loc(s)} derivesRule → '{loc(r)}' 가 rules.ttl 에 없음 (CD-3: AggravationRule 잔재?)")

    # 4. 규칙 → 문장, basis 일치
    for rule in rules.subjects(RDF.type, DOM.DesignRule):
        froms = {loc(x) for x in rules.objects(rule, DOM.fromSentence)}
        basis_lit = rules.value(rule, DOM.basis)
        if basis_lit is None:
            errors.append(f"{loc(rule)}: basis 누락")
            continue
        basis = {b.strip() for b in str(basis_lit).split(",")}
        if not froms <= sentences:
            errors.append(f"{loc(rule)}: fromSentence {sorted(froms - sentences)} 가 실재하지 않음")
        if froms != basis:
            errors.append(f"{loc(rule)}: fromSentence {sorted(froms)} != basis {sorted(basis)}")

        pol = str(rules.value(rule, DOM.polarity) or "")
        if pol not in {"cause", "mitigate", "aggravate"}:
            errors.append(f"{loc(rule)}: 극성 '{pol}' 이 허용값 밖")

    # 5. 카테고리 · 게이트 수
    cats = {str(c) for c in rules.objects(None, DOM.category)}
    if cats != EXPECTED_CATEGORIES:
        errors.append(f"카테고리 불일치: {sorted(cats)} != {sorted(EXPECTED_CATEGORIES)}")

    for selected, expected in EXPECTED_GATES.items():
        gates = sum(
            1
            for rule in rules.subjects(RDF.type, DOM.DesignRule)
            if str(rules.value(rule, DOM.category)) in selected
            and str(rules.value(rule, DOM.polarity)) in GATE_POLARITIES
        )
        if gates != expected:
            errors.append(f"지식범위 {sorted(selected)} → 게이트 {gates}개, 기대 {expected}개 (AC-scope)")

    if errors:
        print(f"❌ 시드 일관성 실패 {len(errors)}건\n")
        for e in errors:
            print("  ·", e)
        return 1

    print("✅ 시드 일관성 통과")
    print(f"   문장 {len(sentences)} · 규칙 {len(rule_names)} · 카테고리 {sorted(cats)}")
    print(f"   게이트: {{소음,떨림}}=4 · {{떨림}}=3 (AC-scope 일치)")
    print("   규칙 단일 진실원 = rules.ttl (CD-3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
