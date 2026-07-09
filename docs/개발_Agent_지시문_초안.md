# PKMS 통합 — 개발 Agent 지시문 초안 (03_dev_team 스쿼드 연결)

> 작성일 2026-07-09 · **상태 v1 (확정)** · 03_dev_team 스쿼드에 넘길 개발 지시문(확정). 착수는 **Windows PowerShell + Claude Code + GitHub** — 절차는 [START-devteam-windows.md] + `setup-dev.ps1`.

## 1. 역할 · 목표
SRS·기술설계·수용기준을 입력받아, **계약 먼저 고정 → 병렬 구현 → 통합 게이트**로 PKMS 통합 시스템을 구현한다. 핵심 루프 **SC-1(입력·검증) → SC-2(satisfy) → SC-3(환각비교)** 를 화면에서 끝까지 동작시키는 것이 1차 목표.

## 2. 입력 문서
- `개발_요구사항_명세서.md`(SRS) · `기술_설계_명세서.md` · `수용기준_및_테스트_시나리오.md`
- 배경: 재기획 `Phase0~5` + 검토문서(`RB-저작-검토`·`DesignRule-SHACL-단일소스-검토`·`지식-저작-상호작용-검토`) + `ttl-demo/`(**satisfy_demo·gen_shacl·project_scope_demo** — 참조 구현체)

## 3. 팀 매핑 (dev_team 스쿼드 → 이 아키텍처)

| # | Agent | 이 프로젝트에서 담당 |
|---|-------|----------------------|
| 00 | 오케스트레이터 | 작업분해·계약변경 통제·통합 게이트 |
| 01 | 아키텍처·표준 | 리포 골격(frontend/bff/knowledge) + **계약 freeze**: BFF↔지식서비스 API·에러모델·스키마 |
| 02 | 데이터 | 6문장 시드 TTL(m0/m1/shapes) 적재·정규화 |
| 03 | RAG·지식 | 임베딩(다국어 ST/MOCK)·Chroma·하이브리드 검색·충분성 · **지식 카테고리·프로젝트 지식선택** |
| 04 | 그래프·코어 | Oxigraph·owlready2/HermiT·pySHACL·**satisfy 엔진·규칙 컴파일러(문장→규칙→SHACL)**(ttl-demo 이식) |
| 05 | 백엔드·API | Node BFF(라우트·SSE·AI Gateway) + Python FastAPI 엔드포인트 |
| 06 | 퍼시스턴스 | Oxigraph 영속·시드 자동적재·벡터 인덱스 동기 |
| 07 | 프론트엔드 | React 화면(Phase 4 IA) — 핵심 3화면 목업 참조 |
| 08 | QA | 수용기준·회귀셋(regression_set.jsonl)·LLM-as-Judge·실패 케이스 |
| 09 | DevOps | Docker compose(3서비스+HermiT JRE)·로컬=Docker 패리티 |

## 4. 작업 순서 & 게이트
```
Phase 0 (직렬)  01 계약 freeze [G0]  — BFF↔지식서비스 계약·에러·스키마·mock fixtures
Phase 1 (병렬)  02 시드 │ 03 RAG │ 06 퍼시스턴스 │ 04 그래프·코어(satisfy) [G1 인터페이스 적합]
Phase 2 (통합)  05 API(BFF+FastAPI 결합, /extraction·/satisfy·/qa) → 07 프론트 [G2 E2E]
Phase 3 (검증)  08 QA(상시·게이트) │ 09 DevOps(패키징)
```
- 임계 경로: 01 계약 → 04 satisfy 코어 → 05 API → 08 QA → 09 패키징.
- 04는 `ttl-demo/satisfy_demo.py`를 서비스화(참조 구현 존재 → 리스크 낮음).

## 5. 제약 (반드시 지킴)
- **레이어 분리**: 지식·추론·RAG는 Python 서비스에만. Node BFF는 오케스트레이션·생성·SSE.
- **내부 구조 비노출**: 지식서비스는 내부(BFF만 외부 노출). API 버저닝(`/api/v1`).
- **시크릿 분리**: API 키는 컨테이너 env(코드·`.env`·git·이미지 금지, 로그 마스킹).
- **MOCK 우선**: 키 없이 Mock으로 전 흐름 동작해야 함(추출·Q&A·임베딩).
- **결정론 우선**: satisfy·검증은 reasoner/SHACL가 판정, LLM은 생성만.
- **테스트 우선**: 회귀셋(satisfy good/bad·추출 range 위반) 먼저.
- **한글**: 모든 커뮤니케이션·산출물 한글.

## 6. 완료 정의 (DoD)
- 핵심 루프 SC-1→2→3가 화면에서 처음부터 끝까지 동작.
- **satisfy good ✅ / bad ⛔(S1·S3·S4·S6)** 를 UI·API에서 재현.
- 문장 편집 → 규칙·SHACL 재파생. **프로젝트 지식범위**로 satisfy 결과 달라짐(A=4/B=3위반) 재현.
- 회귀셋(`regression_set.jsonl`) 전건 통과.
- Mock 모드로 키 없이 전 흐름 동작 + Docker compose 로컬=배포 동일.
- P0 시나리오별 수용기준(AC-1~8) 충족.

## 7. 실행 · GitHub · 보안 (착수)

- **실행 환경**: Windows PowerShell에서 Claude Code(`claude`)로 **신규 리포 `Working\pkms-integrated`** 에서 착수. 셋업·킥오프 프롬프트는 [START-devteam-windows.md] + `setup-dev.ps1`.
- **GitHub**: 리포를 GitHub(private)에 연결(`main`/`develop`). **개발 중 커밋·푸시 상시** — 각 게이트(G0~G2)·에이전트 단계 완료마다 한글 커밋 + `origin/develop` 푸시. 게이트 태그(`g0-contracts`·`g1-*`·`g2-e2e`). PR은 재현님 요청 시에만.
- **git 워크플로**: `main`(안정)·`develop`(개발), 에이전트/단계별 feature 브랜치 → develop 머지.
- **보안**: API 키(ANTHROPIC/GOOGLE_AI)는 **Windows 사용자 환경변수**(`setx`). 코드·`.env`·git·이미지에 키 금지, 로그 마스킹. `.gitignore`에 `.env` 계열 포함.
- **G0 착수 내용**: 오케스트레이터가 리포 골격(frontend/bff/knowledge) + `_coordination/contracts/` 계약 freeze → 커밋·푸시·`g0-contracts` 태그 → G0 게이트 보고 후 Phase 1 병렬 착수 승인 요청.

---
*확정 v1. 재현님이 [START-devteam-windows.md]대로 Windows PowerShell에서 착수하면, 오케스트레이터가 이 문서와 3개 명세를 입력으로 G0부터 시작한다.*
