# MacroLens 개발 스쿼드 — Agent 팀 구성

> 단일 개발 Agent 대신 **오케스트레이터 + 전문 Agent**로 병렬 개발한다.
> 원칙: **계약 먼저 고정 → 병렬 구현 → 통합 게이트**. 모든 협업은 공유 파일 + 오케스트레이터로 이뤄진다.
> 입력 근거: `deliverables/개발준비/`(SRS·기술설계·수용기준), `docs/`, `rag_corpus/`.

## 팀 로스터

| # | Agent | 책임(한 문장) | 담당 코드 경로 |
|---|---|---|---|
| 00 | **오케스트레이터** | 작업 분해·할당·의존성·통합 게이트·계약 변경 통제 | `_coordination/` 전체 |
| 01 | 아키텍처·표준 | 레포 골격 + 공유 계약(API·인터페이스·에러·State) 고정 | `core/`, 레포 루트, 계약 |
| 02 | 데이터 | 외부 소스 클라이언트·캐시·정규화 | `backend/app/data/` |
| 03 | RAG·지식 | 청킹·임베딩·Chroma·가중/시차 검색·충분성 | `backend/app/rag/` |
| 04 | 그래프·코어 | LangGraph State·노드·라우팅 + LLM provider·프롬프트 | `backend/app/graph/`, `llm/` |
| 05 | 백엔드·API | FastAPI 엔드포인트·SSE·예외·lifespan | `backend/app/api/`, `main.py` |
| 06 | 퍼시스턴스(DB·FS) | SQLite 스키마(히스토리·핀)·파일 레이아웃·마이그레이션 | `backend/app/store/`, FS 설계 |
| 07 | 프론트엔드 | Streamlit IA·컴포넌트·SSE 소비·에러 UX | `frontend/` |
| 08 | QA·시나리오테스트 | 수용기준·회귀셋·LLM-as-Judge·실패 케이스 | `backend/tests/`, 평가 |
| 09 | DevOps·패키징 | Docker·compose·로컬=Docker 패리티·env 배선 | `Dockerfile`, `docker-compose.yml` |

## 병렬화 단계 (의존성 요약, 상세는 `작업분해_의존성맵.md`)

```
Phase 0 (직렬·차단)   01 아키텍처·표준 → [계약 freeze 게이트]
Phase 1 (병렬)        02 데이터 │ 03 RAG │ 06 퍼시스턴스 │ 04 그래프·코어(모의 의존)
Phase 2 (통합)        05 백엔드·API(04+06 결합) → 07 프론트(API 소비, 모의 선행)
Phase 3 (검증·패키징) 08 QA(상시·게이트) │ 09 DevOps(최종 패키징)
```

핵심: **계약(인터페이스·API)을 Phase 0에서 고정**하면 02·03·04·06이 서로를 기다리지 않고 **모의(mock) 구현**으로 병렬 진행할 수 있다.

## 협업 방식

- 단일 진실 소스 = 레포 + `deliverables/개발/_coordination/`.
- 계약은 `_coordination/contracts/`에 **버전 고정**. 변경은 오케스트레이터 승인 + 버전업 + 의존 Agent 통지(`통신_프로토콜.md`).
- 작업 보드 `_coordination/task_board.md`(오케스트레이터 소유), 각 Agent 상태 `_coordination/status/<agent>.md`.
- 통합 결과는 `_coordination/integration_log.md`.

## 파일 안내

- `00_오케스트레이터_지시문.md` — 매니저 Agent
- `01~09_*.md` — 전문 Agent 지시문
- `통신_프로토콜.md` — 메시지 양식·계약 변경 절차
- `작업분해_의존성맵.md` — 작업 DAG·게이트
- `공유표준/` — API 표준·인터페이스 계약·상태보고 양식
