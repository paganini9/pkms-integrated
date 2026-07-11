"""satisfy 엔진 — `ontology-ref/satisfy_demo.py` 의 3단계 판정을 서비스화한다.

  (1) 정성 subsumption   — 재질 기반 (실리콘 ⊑ 저소음 / 고무 ∧ 겨울 → 소음)
  (2) SHACL 게이트 + 구간 비교기 — 결정론적 수치 판정
  (3) 무증상 규칙        — 유발 증상 ∩ 요구가 금지한 증상 = ∅ 인가

**판정 주체는 reasoner/SHACL 이다. LLM 은 이 파일에 관여하지 않는다.**
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from pathlib import Path

import pyshacl
from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef, XSD

from core.config import settings
from core.logging import get_trace_id
from reasoning.compiler import CompiledRules, RuleCompiler
from reasoning.rules import Cond, RuleSpec, loc, normalize_violations, sentence_sort_key
from schemas.errors import ReasonerError
from schemas.models import (
    Design,
    ExhibitedSymptom,
    IntervalCheck,
    SatisfyResponse,
    ShaclIntervalStep,
    SubsumptionStep,
    SymptomFreeStep,
    ViolatedRequirement,
    Violation,
)

log = logging.getLogger("knowledge.satisfy")

DOM = Namespace("http://ex.org/domain#")
ENG = Namespace("http://ex.org/eng#")
SPMM = Namespace("http://ex.org/spmm#")
SH = Namespace("http://www.w3.org/ns/shacl#")

DESIGN_IRI = ENG["_design_under_test"]

# 설계 필드 → RDF 술어. 수치는 xsd:integer 로 넣어야 FILTER(?l > ?m) 가 성립한다.
_OBJECT_FIELDS = {"material": DOM.hasMaterial, "vehicle": DOM.mountedOn, "env": DOM.operatesIn}
_LITERAL_FIELDS = {
    "length_mm": (DOM.lengthMm, XSD.integer),
    "spring_n": (DOM.springN, XSD.integer),
    "arm_shape": (DOM.armShape, XSD.string),
}

# 대안 문구는 와이퍼 도메인에 특화돼 있다. 도메인이 늘면 규칙 메타데이터로 옮긴다.
_ALTERNATIVE_BY_PATH = {
    "lengthMm": "길이→차종 안전길이 이내",
    "springN": "스프링→≥10N",
    "armShape": "암형상→complex",
}


class MissingRequired(Exception):
    """수치 결측 — 판정 보류(pending). 에러가 아니라 정상 흐름이다."""

    def __init__(self, warnings: list[Violation]) -> None:
        super().__init__("필수 수치 결측")
        self.warnings = warnings


def _design_graph(design: Design) -> Graph:
    g = Graph()
    g.add((DESIGN_IRI, RDF.type, DOM.WiperBlade))
    g.add((DESIGN_IRI, RDFS.label, Literal(design.label or design.id or "검증 대상 설계")))
    for field, pred in _OBJECT_FIELDS.items():
        value = getattr(design, field, None)
        if value:
            g.add((DESIGN_IRI, pred, DOM[value]))
    for field, (pred, dt) in _LITERAL_FIELDS.items():
        value = getattr(design, field, None)
        if value is not None:
            g.add((DESIGN_IRI, pred, Literal(value, datatype=dt)))
    return g


class SatisfyEngine:
    """`core.protocols.SatisfyEngine` 구현.

    시그니처 캐시: sha256(설계 정규형 + 요구 + 카테고리 + shapes 해시).
    reasoner 지연(수십 초)을 흡수하는 NFR 장치다.
    """

    def __init__(self, compiler: RuleCompiler | None = None, ontology_dir: Path | None = None) -> None:
        self._dir = ontology_dir or settings.ontology_dir
        self.compiler = compiler or RuleCompiler(self._dir)
        self._cache: OrderedDict[str, SatisfyResponse] = OrderedDict()

        # 상위 온톨로지 + 도메인 (차종 maxSafeLengthMm 등 상위 데이터를 게이트가 함께 봐야 한다)
        self._onto = Graph()
        for name in ("m0.ttl", "m1_wiper.ttl"):
            self._onto.parse(self._dir / name, format="turtle")

        # 요구거동(RB) 정의는 M2 프로젝트 데이터에 있다. 설계 인스턴스는 요청마다 새로 만든다.
        self._m2 = Graph().parse(self._dir / "m2_instances.ttl", format="turtle")
        self._requirements = {
            loc(rb): {
                "iri": rb,
                "label": str(self._m2.value(rb, RDFS.label) or loc(rb)),
                "forbids": loc(self._m2.value(rb, DOM.forbidsSymptom)),
            }
            for rb in self._m2.subjects(RDF.type, SPMM.RequiredBehavior)
        }

    # ── 캐시 ──────────────────────────────────────────────────────────────
    def _signature(self, design: Design, require: list[str], compiled: CompiledRules) -> str:
        payload = json.dumps(
            {
                "design": design.model_dump(exclude_none=True),
                "require": sorted(require),
                "categories": compiled.applied_categories,
                "shapes": compiled.shapes_hash,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ── (1) 정성 subsumption ──────────────────────────────────────────────
    def _subsumption(self, design: Design, compiled: CompiledRules) -> SubsumptionStep:
        material_rules = [r for r in compiled.applied_rules if any(c.path == "hasMaterial" for c in r.conds)]
        if not material_rules:
            skipped = sorted({r.category for r in self.compiler.rules} - set(compiled.applied_categories))
            reason = f"{'·'.join(skipped)} 카테고리 미적용" if skipped else "정성 규칙 없음"
            return SubsumptionStep(ok=True, detail=f"{reason} — 정성 판정 대상 없음")

        # 해소(mitigate)가 먼저다 — 실리콘이면 소음 원인 규칙을 볼 필요가 없다.
        for rule in material_rules:
            if rule.polarity == "mitigate" and self._conds_match(design, rule.conds):
                return SubsumptionStep(ok=True, detail=f"{rule.label} ({rule.basis})")
        for rule in material_rules:
            if rule.makes_gate and self._conds_match(design, rule.conds):
                return SubsumptionStep(ok=False, detail=f"{rule.label} ({rule.basis})")
        return SubsumptionStep(ok=True, detail="해당 없음")

    def _conds_match(self, design: Design, conds: tuple[Cond, ...]) -> bool:
        for c in conds:
            if c.op != "eq":
                return False  # 수치 조건은 (2)단계 소관
            field = _field_for_path(c.path)
            actual = getattr(design, field, None) if field else None
            if actual is None or str(actual) != loc(c.val):
                return False
        return True

    # ── (2) SHACL 게이트 + 구간 비교기 ────────────────────────────────────
    def _interval_checks(self, design: Design, compiled: CompiledRules) -> list[IntervalCheck]:
        checks: list[IntervalCheck] = []
        warnings: list[Violation] = []

        for rule in compiled.applied_rules:
            for cond in rule.conds:
                if not cond.is_numeric:
                    continue
                check, warning = self._numeric_check(design, rule, cond)
                if warning is not None:
                    warnings.append(warning)
                elif check is not None:
                    checks.append(check)

        if warnings:
            raise MissingRequired(warnings)
        return checks

    def _numeric_check(self, design: Design, rule: RuleSpec, cond: Cond) -> tuple[IntervalCheck | None, Violation | None]:
        field = _field_for_path(cond.path)
        actual = getattr(design, field, None) if field else None
        if actual is None:
            return None, Violation(
                code="missing_required",
                severity="warning",  # CD-7: 저장/판정을 막지 않는 정보성 — 대신 판정을 보류한다
                offender=cond.path,
                message=f"{cond.path} 값이 없어 규칙({rule.basis})을 판정할 수 없습니다. 값을 입력하면 최종 판정이 나옵니다.",
                sentence=rule.basis,
                source_shape=rule.shape_id,
            )

        if cond.op == "gtPath":
            # 위반 조건: this.path > this.p1.p2  →  통과 조건: actual ≤ 상한
            p1, p2 = cond.ref_list
            ref_node = getattr(design, _field_for_path(p1) or "", None)
            limit = self._onto.value(DOM[ref_node], DOM[p2]) if ref_node else None
            if limit is None:
                return None, Violation(
                    code="missing_required",
                    severity="warning",
                    offender=p2,
                    message=f"{ref_node} 의 {p2} 를 온톨로지에서 찾을 수 없어 규칙({rule.basis})을 판정할 수 없습니다.",
                    sentence=rule.basis,
                    source_shape=rule.shape_id,
                )
            limit_v = int(limit)
            return IntervalCheck(
                name=f"길이 구간포함 {cond.path} ≤ maxSafe", expr=f"{actual} ≤ {limit_v}", ok=actual <= limit_v
            ), None

        # 위반 조건이 `actual op val` 이므로, 통과 조건은 그 부정이다.
        inverse = {"lt": "≥", "le": ">", "gt": "≤", "ge": "<"}[cond.op]
        threshold = int(cond.val)  # type: ignore[arg-type]
        passes = {
            "lt": actual >= threshold,
            "le": actual > threshold,
            "gt": actual <= threshold,
            "ge": actual < threshold,
        }[cond.op]
        return IntervalCheck(
            name=f"스프링 임계 {cond.path} {inverse} {threshold}" if cond.path == "springN"
            else f"{cond.path} {inverse} {threshold}",
            expr=f"{actual} {inverse} {threshold}",
            ok=passes,
        ), None

    # ── (3) 무증상 규칙 ───────────────────────────────────────────────────
    def _run_gates(self, data: Graph, compiled: CompiledRules) -> dict[URIRef, list[str]]:
        """pySHACL 로 게이트를 실행하고 focus 노드별 위반 shape_id 를 돌려준다."""
        try:
            _conforms, report, _text = pyshacl.validate(
                data_graph=data,
                # 정본이 아니라 사본을 넘긴다 — pySHACL 은 넘겨받은 shapes 그래프에 트리플을 주입한다.
                # 정본을 주면 shapes_hash 가 매 호출마다 바뀌어 satisfy 캐시가 빗나가고,
                # /rules/compile 이 돌려주는 shapes_ttl 이 호출할수록 부풀어 오른다.
                shacl_graph=compiled.shapes_copy(),
                ont_graph=None,
                inference="none",
                advanced=True,
                meta_shacl=False,
            )
        except Exception as exc:  # pragma: no cover - pyshacl 내부 오류
            raise ReasonerError(f"pySHACL 실행 실패: {exc}") from exc

        by_focus: dict[URIRef, list[str]] = {}
        for result in report.subjects(RDF.type, SH.ValidationResult):
            focus = report.value(result, SH.focusNode)
            owner = self._owner_shape(compiled, report.value(result, SH.sourceShape))
            if owner:
                by_focus.setdefault(focus, []).append(owner)

        # SHACL 리포트는 순서를 보장하지 않는다. 같은 입력 → 같은 출력(NFR 재현성)을 위해
        # 근거 문장 번호로 정렬한다 → S1, "S3,S5", S4, S6 순.
        for focus, shapes in by_focus.items():
            by_focus[focus] = sorted(
                shapes, key=lambda s: sentence_sort_key(compiled.gates[s].basis.split(",")[0])
            )
        return by_focus

    def _fired_gates(self, design: Design, compiled: CompiledRules) -> list[str]:
        data = Graph()
        for t in self._onto:
            data.add(t)
        for t in _design_graph(design):
            data.add(t)
        return self._run_gates(data, compiled).get(DESIGN_IRI, [])

    # ── dry-run (AC-7) ────────────────────────────────────────────────────
    def dry_run(self, override: Graph, categories: set[str] | None = None) -> tuple[list[str], list[str]]:
        """규칙·수치 변경을 임시 그래프에 적용해 **새로 생기는 위반**을 미리 본다. 저장하지 않는다.

        예: `dom:MidSizeSUV dom:maxSafeLengthMm 595` → 기존 599 를 덮어쓰고 M2 설계들을 재검사.
        """
        compiled = self.compiler.compile(categories)

        baseline_data = Graph()
        for t in self._onto:
            baseline_data.add(t)
        for t in self._m2:
            baseline_data.add(t)

        modified = Graph()
        for t in baseline_data:
            modified.add(t)
        for s, p, o in override:
            modified.remove((s, p, None))  # 덮어쓰기 — 값 추가가 아니다
            modified.add((s, p, o))

        before = self._run_gates(baseline_data, compiled)
        after = self._run_gates(modified, compiled)

        new_violations: list[str] = []
        affected: list[str] = []
        for focus, shapes in sorted(after.items(), key=lambda kv: str(kv[0])):
            fresh = [s for s in shapes if s not in before.get(focus, [])]
            if not fresh:
                continue
            label = str(modified.value(focus, RDFS.label) or loc(focus))
            affected.append(loc(focus))
            new_violations.extend(f"{label} — {compiled.gates[s].message}" for s in fresh)

        return new_violations, affected

    @staticmethod
    def _owner_shape(compiled: CompiledRules, source: URIRef | None) -> str | None:
        """sh:sparql 은 블랭크노드라 sourceShape 가 그것을 가리킬 수 있다 → 소속 NodeShape 역추적."""
        if source is None:
            return None
        if isinstance(source, URIRef) and loc(source) in compiled.gates:
            return loc(source)
        for shape in compiled.shapes.subjects(RDF.type, SH.NodeShape):
            if (shape, SH.sparql, source) in compiled.shapes:
                return loc(shape)
        return None

    # ── 판정 ──────────────────────────────────────────────────────────────
    def satisfy(
        self, design: Design, require: list[str], categories: set[str] | None = None
    ) -> SatisfyResponse:
        compiled = self.compiler.compile(categories)
        require = list(require) or sorted(self._requirements)
        signature = self._signature(design, require, compiled)

        if signature in self._cache:
            self._cache.move_to_end(signature)
            cached = self._cache[signature].model_copy(update={"cache_hit": True, "trace_id": get_trace_id()})
            log.info("satisfy 캐시 히트 %s", signature[:8])
            return cached

        result = self._compute(design, require, compiled)
        self._cache[signature] = result
        if len(self._cache) > settings.satisfy_cache_size:
            self._cache.popitem(last=False)
        return result

    def _compute(self, design: Design, require: list[str], compiled: CompiledRules) -> SatisfyResponse:
        justification: list[str] = []
        if compiled.applied_categories:
            justification.append(f"적용 지식범위: {compiled.applied_categories} · 게이트 {len(compiled.gates)}개")

        step1 = self._subsumption(design, compiled)
        justification.append(f"(1) 정성 subsumption {'✔' if step1.ok else '✘'} — {step1.detail}")

        # (2) 수치 결측이면 판정 보류 — 부분 판정을 확정으로 승격하지 않는다.
        try:
            checks = self._interval_checks(design, compiled)
        except MissingRequired as pending:
            return SatisfyResponse(
                satisfies=None,
                pending_reason="missing_required",
                applied_categories=compiled.applied_categories,
                steps=[
                    step1,
                    ShaclIntervalStep(ok=False, checks=[], warnings=pending.warnings),
                    SymptomFreeStep(ok=False, exhibited=[]),
                ],
                violations=[],
                violation_bases=[],
                violated_requirements=[],
                alternatives=[],
                justification=justification + [w.message for w in pending.warnings],
                cache_hit=False,
                trace_id=get_trace_id(),
            )

        step2 = ShaclIntervalStep(ok=all(c.ok for c in checks), checks=checks)
        for c in checks:
            justification.append(f"(2) 수치 게이트 {'✔' if c.ok else '✘'} — {c.name} ({c.expr})")

        # (3) 게이트 실행 → 유발 증상
        fired = self._fired_gates(design, compiled)
        exhibited_map: dict[str, list[str]] = {}
        for shape_id in fired:
            gate = compiled.gates[shape_id]
            exhibited_map.setdefault(gate.symptom, []).append(gate.basis)

        exhibited = [
            ExhibitedSymptom(
                symptom=symptom,
                label=str(self._onto.value(DOM[symptom], RDFS.label) or symptom),
                sentences=sorted(set(bases), key=lambda b: sentence_sort_key(b.split(",")[0])),
            )
            for symptom, bases in exhibited_map.items()
        ]
        step3 = SymptomFreeStep(ok=not exhibited, exhibited=exhibited)
        justification.append(
            "(3) 무증상 규칙 ✘ — 유발 증상: "
            + ", ".join(f"{e.label}[{'·'.join(e.sentences)}]" for e in exhibited)
            if exhibited
            else "(3) 무증상 규칙 ✔ — 유발 증상 없음"
        )

        # 요구(RB)가 금지한 증상을 유발했는가
        violated: list[ViolatedRequirement] = []
        for rb_id in require:
            rb = self._requirements.get(rb_id)
            if rb is None:
                log.warning("알 수 없는 요구거동 %s — 무시", rb_id)
                continue
            if rb["forbids"] in exhibited_map:
                violated.append(
                    ViolatedRequirement(
                        rb=rb_id,
                        label=rb["label"],
                        forbids=rb["forbids"],
                        sentences=sorted(
                            set(exhibited_map[rb["forbids"]]), key=lambda b: sentence_sort_key(b.split(",")[0])
                        ),
                    )
                )

        satisfies = not violated
        bases = [b for v in violated for b in v.sentences]
        violations = normalize_violations(bases, self.compiler.sentence_polarity)

        justification.append(
            f"판정: DB {'⊑' if satisfies else '⋢'} " + " ⊓ ".join(require) if require else "판정: 요구 없음"
        )

        return SatisfyResponse(
            satisfies=satisfies,
            pending_reason=None,
            applied_categories=compiled.applied_categories,
            steps=[step1, step2, step3],
            violations=violations,
            violation_bases=sorted(set(bases), key=lambda b: sentence_sort_key(b.split(",")[0])),
            violated_requirements=violated,
            alternatives=self._alternatives(exhibited_map, fired, compiled),
            justification=justification,
            cache_hit=False,
            trace_id=get_trace_id(),
        )

    # ── 허용 대안 ─────────────────────────────────────────────────────────
    def _alternatives(
        self, exhibited: dict[str, list[str]], fired: list[str], compiled: CompiledRules
    ) -> list[str]:
        alts: list[str] = []
        for symptom in exhibited:
            # 해소(mitigate) 규칙이 있으면 그것이 1순위 대안이다.
            for rule in compiled.applied_rules:
                if rule.polarity == "mitigate" and rule.symptom == symptom:
                    mat = next((loc(c.val) for c in rule.conds if c.path == "hasMaterial"), None)
                    label = str(self._onto.value(DOM[mat], RDFS.label) or mat) if mat else rule.label
                    korean = label.split("(")[-1].rstrip(")") if "(" in label else label
                    alts.append(f"재질→{korean}({rule.basis})")

        for shape_id in fired:
            gate = compiled.gates[shape_id]
            rule = next(r for r in compiled.applied_rules if r.id == gate.rule_id)
            for cond in rule.conds:
                phrase = _ALTERNATIVE_BY_PATH.get(cond.path)
                if not phrase:
                    continue
                if cond.op == "gtPath":
                    # 해소 문장(mitigate)을 근거로 붙인다 — 예: 길이 대안의 근거는 S5
                    mitigate_codes = [
                        c for c in rule.basis_sentences if self.compiler.sentence_polarity.get(c) == "mitigate"
                    ]
                    suffix = f"({mitigate_codes[0]})" if mitigate_codes else ""
                    alts.append(f"{phrase}{suffix}")
                else:
                    alts.append(phrase)
        # 중복 제거하되 순서 유지
        return list(dict.fromkeys(alts))


def _field_for_path(path: str) -> str | None:
    """RDF 술어 로컬네임 → Design 필드명."""
    for field, pred in _OBJECT_FIELDS.items():
        if loc(pred) == path:
            return field
    for field, (pred, _dt) in _LITERAL_FIELDS.items():
        if loc(pred) == path:
            return field
    return None
