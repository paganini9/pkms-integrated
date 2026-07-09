# mock fixtures — v1 freeze

계약(`api_standard.md`·`interface_contracts.md`)을 만족하는 **고정 정답 샘플**. 의존 레이어가 미완이어도 각 Agent가 이 fixture로 선행 개발한다.
테스트가 직접 참조하므로 **임의 변경 금지** — 변경은 계약 변경 절차(`통신_프로토콜.md` `contract-change`).

| 파일 | 대응 | 쓰는 Agent |
|---|---|---|
| `health.json` | `GET /api/v1/health` | 05·07·09 |
| `extraction_stream_S1.json` | `POST /extraction/stream` SSE 이벤트 순열 (AC-1 정상) | 05·07 |
| `extraction_validate_range_violation.json` | `POST /extraction/validate` (AC-1 range 위반 · 회귀 `ext-range`) | 04·05·07 |
| `extraction_save_S1.json` | `POST /extraction/save` (문장→규칙→SHACL 파생, AC-1) | 04·05·06·07 |
| `satisfy_bad.json` | AC-2 설계 A ⛔ (회귀 `sat-bad`) | 04·05·07·08 |
| `satisfy_good.json` | AC-2 설계 B ✅ (회귀 `sat-good`) | 04·05·07·08 |
| `satisfy_scope_B.json` | AC-scope 프로젝트 B(떨림만) — 3위반 | 04·05·08 |
| `satisfy_pending_missing.json` | 수치 누락 → 판정 보류 | 04·05·07 |
| `qa_layerA_599.json` | AC-3 A계층 (회귀 `qa-A`) | 05·07·08 |
| `qa_compare_suv600.json` | AC-3 환각비교 (B계층) | 05·07·08 |
| `qa_insufficient.json` | 도메인 밖 질의 → "명세 근거 없음" | 05·07·08 |
| `graph_tipchatter.json` | AC-4 지식맵 (S3 클릭, inferred 점선 포함) | 05·07 |
| `project_requirements_parse.json` | AC-1P 자연어→RB 파싱 | 05·07 |
| `rag_search_winter_rubber.json` | `POST /rag/search` (verified 필터·충분성) | 03·05 |
| `error_llm_timeout.json` | `LLM_TIMEOUT` 에러 본문 | 05·07 |
| `regression_set.jsonl` | 08 QA 회귀셋 **시드** (수용기준 §3 + CD-1 정규화 반영) | 08 |

## `_` 접두 키 규약

fixture의 `_comment`·`_request`·`_note`·`_variant_*` 는 **문서용 메타 키**이며 응답 본문의 일부가 아니다.
스키마는 `additionalProperties: false` 이므로, mock을 서빙하거나 스키마 검증할 때는 **최상위 `_` 접두 키를 제거**한 뒤 사용한다.
`_request` 는 그 fixture가 어떤 요청에 대한 응답인지를 못 박아 두는 용도다(테스트 입력으로 재사용 가능).

## 정규화 주의 (CD-1)

`satisfy` 응답은 두 필드를 함께 싣는다.
- `violations` = `["S1","S3","S4","S6"]` — 개별 문장 코드, 극성 `cause`·`aggravate`만
- `violation_bases` = `["S1","S3,S5","S4","S6"]` — 게이트의 원본 basis

수용기준 §3 회귀셋 원문의 `scope-*` 기대값은 **`violation_bases`** 를 가리킨다. 시드 jsonl은 이를 필드명으로 명시했다.
