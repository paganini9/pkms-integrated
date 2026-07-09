#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PKMS 온톨로지 백본 — reasoner 로 satisfy 실증.
  (A) OWL RL 추론: 분류·transitive·punning
  (B) 일관성/disjoint 검사
  (C) SHACL 게이트(pySHACL) : 6문장 규칙을 CWA로 실행
  (D) satisfy 3단계 결합: 정성 subsumption + 수치 게이트·구간 비교기 + 무증상 규칙
"""
import os, sys
from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef, Literal
import owlrl, pyshacl

SPMM = Namespace("http://ex.org/spmm#")
EXT  = Namespace("http://ex.org/spmm-ext#")
DOM  = Namespace("http://ex.org/domain#")
ENG  = Namespace("http://ex.org/eng#")
SH   = Namespace("http://www.w3.org/ns/shacl#")
HERE = os.path.dirname(os.path.abspath(__file__))
def p(x): return os.path.join(HERE, x)

def local(u): return str(u).split('#')[-1] if u else str(u)
def label(g, s):
    l = g.value(s, RDFS.label)
    return str(l) if l else local(s)

out = []
def say(s=""):
    print(s); out.append(s)

# ---------- load ----------
onto = Graph()
onto.parse(p("ontology/m0.ttl"), format="turtle")
onto.parse(p("ontology/m1_wiper.ttl"), format="turtle")
data = Graph(); data.parse(p("ontology/m2_instances.ttl"), format="turtle")
shapes = Graph(); shapes.parse(p("ontology/shapes.ttl"), format="turtle")
say(f"로드: onto {len(onto)} triples · data {len(data)} triples · shapes {len(shapes)} triples")
# data + onto 병합 그래프 (SHACL SPARQL·구간 비교기가 차종 maxSafeLengthMm 등 상위 데이터를 함께 보게)
full = Graph()
for t in onto: full.add(t)
for t in data: full.add(t)

# ---------- (A) OWL RL 추론 ----------
say("\n" + "="*68)
say("(A) OWL RL 추론 — 분류 · 이행(transitive) · punning")
say("="*68)
inf = Graph()
for t in onto: inf.add(t)
for t in data: inf.add(t)
owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False,
                       datatype_axioms=False).expand(inf)

def types(g, s):
    ts = [o for o in g.objects(s, RDF.type) if isinstance(o, URIRef)
          and str(o).startswith(("http://ex.org"))]
    return sorted(set(local(t) for t in ts))

say(f"  eng:Blade_good 추론된 타입: {types(inf, ENG.Blade_good)}")
chain_ok = all(t in types(inf, ENG.Blade_good) for t in ["WiperBlade","PartType","Artifact","Entity"])
say(f"    → WiperBlade ⊑ PartType ⊑ Artifact ⊑ Entity 분류 사슬: {'성립 ✔' if chain_ok else '불성립 ✘'}")
trans = (DOM.WipingBehavior, SPMM.has_subbehavior, DOM.ContactBehavior) in inf
say(f"  has_subbehavior 이행: 와이핑 →(추론)→ 접촉 거동 : {'도출 ✔' if trans else '미도출 ✘'}")
pun_c = (DOM.Rubber, RDF.type, OWL.Class) in onto
pun_i = (DOM.Rubber, RDF.type, SPMM.Material) in inf
say(f"  punning: dom:Rubber 가 owl:Class={pun_c} 이면서 spmm:Material 개체={pun_i} : {'성립 ✔' if pun_c and pun_i else '✘'}")

# ---------- (B) 일관성 / disjoint ----------
say("\n" + "="*68)
say("(B) 일관성 · disjoint 검사")
say("="*68)
DISJOINT_SETS = [
    {SPMM.Entity, SPMM.Form, SPMM.Behavior, SPMM.Attribute},
    {SPMM.RequiredBehavior, SPMM.DesignedBehavior, SPMM.TestBehavior},
]
def disjoint_clashes(g):
    clashes = []
    for s in set(g.subjects(RDF.type, None)):
        tset = set(g.objects(s, RDF.type))
        for dset in DISJOINT_SETS:
            hit = tset & dset
            if len(hit) >= 2:
                clashes.append((s, hit))
    return clashes
c = disjoint_clashes(inf)
say(f"  현 온톨로지 disjoint 위반: {len(c)} 건 → {'일관성 OK ✔' if not c else '모순 ✘'}")
# 고의 모순 데모
demo = Graph()
for t in inf: demo.add(t)
demo.add((ENG.Clash, RDF.type, SPMM.Entity))
demo.add((ENG.Clash, RDF.type, SPMM.Behavior))
owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(demo)
c2 = disjoint_clashes(demo)
say(f"  고의 모순(eng:Clash 를 Entity∧Behavior 로): disjoint 위반 {len(c2)} 건 감지 → {'reasoner 가 모순 포착 ✔' if c2 else '✘'}")

# HermiT (있으면)
try:
    import owlready2, tempfile
    tmp = p("_onto_rdfxml.owl")
    onto.serialize(destination=tmp, format="xml")
    w = owlready2.World()
    w.get_ontology("file://" + tmp).load()
    owlready2.sync_reasoner_hermit(w)
    say("  [HermiT/DL] 온톨로지 일관성 검사 통과 ✔ (Java HermiT 실행)")
except Exception as e:
    say(f"  [HermiT/DL] 생략(owlrl 로 대체): {str(e).splitlines()[0][:80]}")

# ---------- (C) SHACL 게이트 ----------
say("\n" + "="*68)
say("(C) SHACL 게이트 (pySHACL) — 6문장 규칙을 CWA 로 실행")
say("="*68)
conforms, rg, rtxt = pyshacl.validate(
    data_graph=full, shacl_graph=shapes, ont_graph=None,
    inference="none", advanced=True, meta_shacl=False)
# shape → symptom, sentence
shape_symptom = {s: shapes.value(s, DOM.gateFor) for s in shapes.subjects(RDF.type, SH.NodeShape)}
shape_sent = {s: str(shapes.value(s, DOM.sentence)) for s in shapes.subjects(RDF.type, SH.NodeShape)}

def collect_violations(report_graph):
    byfocus = {}
    for r in report_graph.subjects(RDF.type, SH.ValidationResult):
        focus = report_graph.value(r, SH.focusNode)
        msg = str(report_graph.value(r, SH.resultMessage))
        src = report_graph.value(r, SH.sourceShape)
        # sourceShape 는 sh:sparql 블랭크노드일 수 있음 → 소속 NodeShape 역추적
        owner = None
        for ns in shapes.subjects(RDF.type, SH.NodeShape):
            if (ns, SH.sparql, src) in shapes or ns == src:
                owner = ns; break
        byfocus.setdefault(focus, []).append((owner, msg))
    return byfocus
viol = collect_violations(rg)
say(f"  전체 conforms = {conforms}  (위반 focus 노드 {len(viol)}개)")
for focus, items in viol.items():
    say(f"   · {label(full, focus)} — 위반 {len(items)}건")
    for owner, msg in sorted(items, key=lambda x: shape_sent.get(x[0], '')):
        say(f"       [{shape_sent.get(owner,'?')}] {msg}")

# ---------- (D) satisfy 3단계 ----------
say("\n" + "="*68)
say("(D) satisfy 판정 — (1)정성 subsumption + (2)수치 게이트·구간 비교기 + (3)무증상 규칙")
say("="*68)

def num(g, s, prop):
    v = g.value(s, prop); return int(v) if v is not None else None
def interval_comparator(g, blade):
    """구간 비교기 — DL 데이터타입 추론을 보완하는 결정론적 수치 판정."""
    checks = []
    length = num(g, blade, DOM.lengthMm)
    veh = g.value(blade, DOM.mountedOn); maxsafe = num(g, veh, DOM.maxSafeLengthMm)
    checks.append(("길이 구간포함 length ≤ maxSafe",
                   f"{length} ≤ {maxsafe}", length is not None and maxsafe is not None and length <= maxsafe))
    spring = num(g, blade, DOM.springN)
    checks.append(("스프링 임계 springN ≥ 10", f"{spring} ≥ 10", spring is not None and spring >= 10))
    return checks

def qualitative_ok(g, blade):
    """정성 subsumption(재질) — 실리콘은 저소음 보장(S2), 고무+겨울은 소음(S1)."""
    mat = g.value(blade, DOM.hasMaterial); env = g.value(blade, DOM.operatesIn)
    if mat == DOM.Silicone:  return True, "재질 실리콘 ⊑ 저소음(S2)"
    if mat == DOM.Rubber and env == DOM.Winter: return False, "재질 고무 ∧ 겨울 → 소음(S1)"
    return True, "해당 없음"

# 프로젝트 요구셋(RB) → 금지 증상  (RB 는 M2 프로젝트 데이터)
PROJECT = ENG.Proj_WinterSUV
RBs = {rb: full.value(rb, DOM.forbidsSymptom) for rb in full.objects(PROJECT, DOM.hasRequirement)}

def satisfy(blade):
    exhibited = {}   # symptom -> [sentences]
    for owner, msg in viol.get(blade, []):
        sym = shape_symptom.get(owner)
        if sym is not None:
            exhibited.setdefault(sym, []).append(shape_sent.get(owner,'?'))
    violated = []
    for rb, forb in RBs.items():
        if forb in exhibited:
            violated.append((rb, forb, exhibited[forb]))
    return (len(violated) == 0), exhibited, violated

for blade in [ENG.Blade_good, ENG.Blade_bad]:
    say(f"\n▶ {label(full, blade)}")
    q_ok, q_why = qualitative_ok(full, blade)
    say(f"  (1) 정성 subsumption : {'✔' if q_ok else '✘'}  — {q_why}")
    say("  (2) 수치 게이트·구간 비교기:")
    for name, expr, ok in interval_comparator(full, blade):
        say(f"        {'✔' if ok else '✘'} {name}  ({expr})")
    ok, exhibited, violated = satisfy(blade)
    if exhibited:
        say("  (3) 무증상 규칙: 유발 증상 → " +
            ", ".join(f"{label(full, sym)}[{'·'.join(sents)}]" for sym, sents in exhibited.items()))
    else:
        say("  (3) 무증상 규칙: 유발 증상 없음")
    say(f"  ── satisfy 판정: {'✅ 만족 (DB ⊑ RB_Winter ⊓ RB_NoChatter)' if ok else '⛔ 불만족'}")
    if violated:
        for rb, forb, sents in violated:
            say(f"       위반 요구: {label(full, rb)} — 금지 증상 '{label(full, forb)}' 유발 (근거 {'·'.join(sents)})")
        # 허용 대안
        alts = []
        if DOM.Noise in exhibited: alts.append("재질→실리콘(S2)")
        if DOM.TipChatter in exhibited:
            alts += ["길이→차종 안전길이 이내(S5)", "스프링→≥10N", "암형상→complex"]
        say(f"       허용 대안: {', '.join(alts)}")

# ---------- save report ----------
with open(p("satisfy_run_output.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
say("\n[저장] satisfy_run_output.txt")
