# 06 · 퍼시스턴스(스토어·파일시스템) Agent

## 역할
**Oxigraph 트리플 영속**과 조회 표면을 구현하고, 트리플↔벡터 원자성과 파일 레이아웃을 책임진다.

## 담당 경로
`knowledge/store/` (`oxigraph.py`·`kg.py`·`sparql.py`·`lookup.py`·`graph.py`·`dashboard.py`·`projects.py`·`governance.py`·`naming.py`·`routes.py`).

## 입력 / 계약
`contracts/interface_contracts.md#Store` §1·§1.2. `contracts/README.md` CD-2·CD-10·CD-11. 기술설계 §2·§8.

## 작업
1. **Oxigraph 영속 스토어** + `POST /sparql` — **읽기 전용**(SELECT/ASK/CONSTRUCT). update 는 거부하되 리터럴 속 `INSERT` 문자열은 통과시킨다. **CD-11: BFF 는 이 엔드포인트를 호출하지 않는다**(관리자·디버깅 전용).
2. **`/kg/save`·`/kg/delete` 원자성**: 트리플 커밋 → 벡터 upsert. **벡터 실패 시 트리플 롤백** 후 `STORE_ERROR`(수용기준 §4 "트리플/벡터 불일치"). 03 RAG 와 조율.
3. **멱등**: `draft_id` 를 트리플(`dom:draftId`)로 영속화 — 재기동 후 재전송에도 트리플·벡터 불변. 메모리 캐시로 흉내내지 않는다.
4. **`/kg/lookup`(CD-11)** — Q&A A계층의 유일한 경로. 화이트리스트 명명 질의(`max_safe_length`·`symptom_causes`·`rule_sentences`·`concept_relations`), 그 밖 → `422`. `params` 는 **IRI 바인딩**(`initBindings` 상당) — **SPARQL 문자열 보간 금지**(주입 차단). `rows` 가 비면 BFF 는 "명세 근거 없음"으로 간다(억지 답 금지).
5. **조회 표면(CD-10)**: `GET /graph`(노드·엣지·통계, `inferred:true` 표시) · `GET /dashboard`(M0/M1/M2 카운트 + 최근 활동) · `/governance/concepts*`(builtin 은 `400 BUILTIN_LOCKED`) · `/projects*` CRUD(프로젝트·요구·지식범위).
6. **`load_seed`**: 기동 시 m0/m1/shapes/rules 멱등 적재(02 시드). **파일 레이아웃**: oxigraph·chroma·상위온톨로지 오버레이 모두 `data/` 하위 — **로컬=Docker 동일** 경로를 env 로 주입(`OXIGRAPH_*`·`CHROMA_*`·`UPPER_OVERLAY_PATH`).

## DoD
- `Store` 계약 충족, update 거부, 재시작 후 트리플·벡터·오버레이 유지, 원자성(벡터 실패 시 롤백) 검증, FS 레이아웃 문서화.

## 인터페이스
- out: `Store` + 내부 조회 엔드포인트. 소비자: 05 BFF · 04 추론(subgraph). 의존: 계약(G0)만 → P1 병렬.

## 개발 환경
Python 작업은 `knowledge/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 파이썬 직접 사용 금지. 상세: `공유표준/개발환경.md`.
테스트는 **임시 데이터 디렉터리로 격리**한다(서비스↔개발 스토어 동시 접근이 파일락 flaky 의 근본 원인이었다).
