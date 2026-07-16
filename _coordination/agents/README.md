# PKMS 통합(와이퍼 지식·온톨로지) 개발 스쿼드 — Agent 팀 구성

> 단일 개발 Agent 대신 **오케스트레이터 + 전문 Agent**로 병렬 개발한다.
> 원칙: **계약 먼저 고정 → 병렬 구현 → 통합 게이트**. 모든 협업은 공유 파일 + 오케스트레이터로 이뤄진다.
> 입력 근거: `docs/`(SRS·기술설계·수용기준·Solar-AI백엔드-통합가이드·임베딩-로컬-전환-지침).

## 서비스 경계 (불변원칙 1 — 상세 `contracts/README.md`)

```
frontend ──/api/v1──▶ bff (Node)  ──HTTP(내부)──▶ knowledge (Python, FastAPI)
                       ├ aiGateway (LLM 생성 전용)   ├ store/     Oxigraph
                       ├ sse                         ├ reasoning/ HermiT·pySHACL·satisfy·규칙컴파일러
                       └ knowledgeClient             └ rag/       Chroma·임베딩
```
**외부 표면은 BFF `/api/v1` 뿐이다.** 지식서비스는 내부 전용.

## 팀 로스터

담당 경로의 진실원은 `contracts/interface_contracts.md` §2 **소유 경로** 표다(병렬 안전 — 남의 경로 수정 금지).

| # | Agent | 책임(한 문장) | 담당 코드 경로 |
|---|---|---|---|
| 00 | **오케스트레이터** | 작업 분해·할당·의존성·통합 게이트·계약 변경 통제 | `_coordination/` 전체 |
| 01 | 아키텍처·표준 | 레포 골격 + 공유 계약(API·인터페이스·에러·스키마·mock) 고정 | `core/`, 레포 루트, `contracts/` |
| 02 | 데이터 | 시드 TTL 적재·정규화(CD-3)·일관성 점검 | `knowledge/ontology/` |
| 03 | RAG·지식 | 임베딩·Chroma·하이브리드 검색·충분성(`verified`) | `knowledge/rag/` |
| 04 | 추론·코어 | satisfy 엔진·규칙 컴파일러·reasoner·SHACL·상위 온톨로지 | `knowledge/reasoning/` |
| 05 | 백엔드·API | BFF(오케스트레이션·AI Gateway·SSE) + 지식서비스 라우팅 표면 | `bff/src/`, `knowledge/main.py`·`schemas/` |
| 06 | 퍼시스턴스 | Oxigraph 영속·트리플/벡터 원자성·조회 표면 | `knowledge/store/` |
| 07 | 프론트엔드 | React 화면·SSE 소비·지식맵·에러 UX | `frontend/src/` |
| 08 | QA·시나리오테스트 | 수용기준·회귀셋·LLM-as-Judge·실패 케이스 | `knowledge/tests/`·`bff/test/`·`_coordination/qa/` |
| 09 | DevOps·패키징 | Docker·compose·로컬=Docker 패리티·CI·env 배선 | `docker-compose.yml`·`*/Dockerfile`·`.github/workflows/` |

> 04 는 Python 추론 코어다. LangGraph 가 아니라 **결정론 엔진**(reasoner·SHACL)이 판정 주체다(불변원칙 3).
> 05 의 BFF 는 **Node/Express** 다. Python 이 아니다.

## 병렬화 단계 (의존성 요약, 상세는 `작업분해_의존성맵.md`)

```
Phase 0 (직렬·차단)   01 아키텍처·표준 → [계약 freeze 게이트 G0]
Phase 1 (병렬)        02 데이터 │ 03 RAG │ 06 퍼시스턴스 │ 04 추론·코어(mock 의존)
Phase 2 (통합)        05 백엔드·API(04+06 결합) → 07 프론트(API 소비, mock 선행)
Phase 3 (검증·패키징) 08 QA(상시·게이트) │ 09 DevOps(최종 패키징)
```

핵심: **계약(인터페이스·API)을 Phase 0에서 고정**하면 02·03·04·06이 서로를 기다리지 않고 **모의(mock) 구현**으로 병렬 진행할 수 있다.
단 **mock 은 계약의 하한이 아니라 계약 그 자체다** — 실제 구현과 같은 입력을 거부해야 한다(`contracts/README.md` §3.1).

## 협업 방식

- 단일 진실 소스 = 레포 + `_coordination/`.
- 계약은 `_coordination/contracts/`에 **버전 고정**. 변경은 오케스트레이터 승인 + 버전업 + 의존 Agent 통지(`통신_프로토콜.md`).
- 작업 보드 `_coordination/task_board.md`(오케스트레이터 소유), 각 Agent 상태 `_coordination/status/<agent>.md`.
- 통합 결과는 `_coordination/integration_log.md`.

## 파일 안내

- `00_오케스트레이터_지시문.md` — 매니저 Agent
- `01~09_*.md` — 전문 Agent 지시문
- `통신_프로토콜.md` — 메시지 양식·계약 변경 절차
- `작업분해_의존성맵.md` — 작업 DAG·게이트
- `공유표준/` — 개발환경·상태보고 양식·Solar 참고. **API·인터페이스 계약은 `contracts/` 가 진실원**(공유표준의 두 문서는 포인터).
