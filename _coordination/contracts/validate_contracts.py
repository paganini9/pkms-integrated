#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계약 자체 검증 — mocks/*.json 이 schemas/*.json 을 실제로 만족하는지 확인한다.

G0 게이트의 기계 검증. 계약을 고치면 이 스크립트가 먼저 깨져야 한다.
CI(09 DevOps)와 08 QA 회귀 파이프라인에서 그대로 호출한다.

    python _coordination/contracts/validate_contracts.py

의존: jsonschema>=4.18 (referencing 기반 registry)
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

# Windows 기본 콘솔(cp949)에서 한글·기호 출력이 깨지지 않도록
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
SCHEMAS = HERE / "schemas"
MOCKS = HERE / "mocks"

BASE = "https://pkms.local/contracts/v1/"


def strip_meta(obj):
    """문서용 `_` 접두 키 제거 (mocks/README.md 규약)."""
    if isinstance(obj, dict):
        return {k: strip_meta(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [strip_meta(x) for x in obj]
    return obj


def load_registry() -> Registry:
    registry = Registry()
    for path in sorted(SCHEMAS.glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


def validator_for(registry: Registry, schema_file: str, definition: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"{BASE}{schema_file}#/$defs/{definition}"}, registry=registry
    )


# (fixture, 스키마 파일, $defs 이름, fixture 안에서 검증할 경로)
# 경로 None = 최상위 문서(메타 키 제거 후). "_request" = 요청 페이로드.
CASES = [
    ("extraction_validate_range_violation.json", "extraction.schema.json", "ValidateResponse", None),
    ("extraction_validate_range_violation.json", "extraction.schema.json", "ValidateRequest", "_request"),
    ("extraction_save_S1.json", "extraction.schema.json", "SaveResponse", None),
    ("extraction_save_S1.json", "extraction.schema.json", "SaveRequest", "_request"),
    ("satisfy_bad.json", "satisfy.schema.json", "SatisfyResponse", None),
    ("satisfy_bad.json", "satisfy.schema.json", "SatisfyRequest", "_request"),
    ("satisfy_good.json", "satisfy.schema.json", "SatisfyResponse", None),
    ("satisfy_good.json", "satisfy.schema.json", "SatisfyRequest", "_request"),
    ("satisfy_scope_B.json", "satisfy.schema.json", "SatisfyResponse", None),
    ("satisfy_pending_missing.json", "satisfy.schema.json", "SatisfyResponse", None),
    ("qa_layerA_599.json", "qa.schema.json", "QaResponse", None),
    ("qa_layerA_599.json", "qa.schema.json", "QaRequest", "_request"),
    ("qa_compare_suv600.json", "qa.schema.json", "QaResponse", None),
    ("qa_insufficient.json", "qa.schema.json", "QaResponse", None),
    ("rag_search_winter_rubber.json", "qa.schema.json", "RagSearchResponse", None),
    ("graph_tipchatter.json", "graph.schema.json", "GraphResponse", None),
    ("project_requirements_parse.json", "project.schema.json", "ParseRequirementsResponse", None),
    ("error_llm_timeout.json", "common.schema.json", "Error", None),
]


def check_stream_events(registry: Registry, failures: list[str]) -> int:
    """SSE fixture 는 이벤트 배열 → 각 data 를 StreamEvent(oneOf)로 검증."""
    doc = json.loads((MOCKS / "extraction_stream_S1.json").read_text(encoding="utf-8"))
    v = validator_for(registry, "extraction.schema.json", "StreamEvent")
    order = [e["event"] for e in doc["events"]]
    for i, ev in enumerate(doc["events"]):
        for err in v.iter_errors(strip_meta(ev["data"])):
            failures.append(f"extraction_stream_S1.json events[{i}] ({ev['event']}): {err.message}")

    # 계약 §5: status* → (concept|relation)* → validation → done
    if order[-1] != "done":
        failures.append("extraction_stream_S1.json: 마지막 이벤트가 done 이 아님")
    if "validation" not in order or order.index("validation") > order.index("done"):
        failures.append("extraction_stream_S1.json: validation 이 done 이전에 없음")
    return len(doc["events"])


def check_cd1_normalization(failures: list[str]) -> None:
    """CD-1: violations 는 violation_bases 를 콤마 분해한 집합의 부분집합이어야 한다."""
    for name in ("satisfy_bad.json", "satisfy_good.json", "satisfy_scope_B.json"):
        doc = json.loads((MOCKS / name).read_text(encoding="utf-8"))
        expanded = {s for base in doc["violation_bases"] for s in base.split(",")}
        if not set(doc["violations"]) <= expanded:
            failures.append(f"{name}: violations {doc['violations']} ⊄ bases 전개 {sorted(expanded)} (CD-1 위반)")
        if doc["violations"] != sorted(doc["violations"]):
            failures.append(f"{name}: violations 가 정렬되어 있지 않음 (CD-1)")


def main() -> int:
    registry = load_registry()
    failures: list[str] = []
    checked = 0

    for fixture, schema_file, definition, path in CASES:
        doc = json.loads((MOCKS / fixture).read_text(encoding="utf-8"))
        payload = strip_meta(doc) if path is None else strip_meta(doc[path])
        v = validator_for(registry, schema_file, definition)
        errs = sorted(v.iter_errors(payload), key=lambda e: list(e.path))
        for err in errs:
            loc = "/".join(str(p) for p in err.path) or "(root)"
            failures.append(f"{fixture} [{definition}] {loc}: {err.message}")
        checked += 1

    checked += check_stream_events(registry, failures)
    check_cd1_normalization(failures)

    if failures:
        print(f"❌ 계약 검증 실패 {len(failures)}건\n")
        for f in failures:
            print("  ·", f)
        return 1

    print(f"✅ 계약 검증 통과 — 스키마 {len(list(SCHEMAS.glob('*.json')))}개 · 검증 {checked}건")
    print("   fixture 가 스키마를 만족하고, CD-1 정규화 불변식이 성립합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
