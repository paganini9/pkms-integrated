# Phase 3 — 검증·패키징 현황 (오케스트레이터)

> 배치·판정 원칙: **실 스택·Solar 실키**로 게이트(mock·Claude 통과만으론 불충분). 결정론 경로에 "값 없으면 채우기" 금지.

## 진행 현황

| id | 태스크 | 상태 | 근거 |
|---|---|:--:|---|
| T-87 | 시드 inferred 엣지 | **done** | `/graph?symptom=TipChatter` inferred_edges=3(AC-4). 지식 98건 |
| T-70 | 회귀셋+실 스택 러너 | **done** | AC-1~8·우회 8종·양성대조. Claude 24 PASS·Solar 우회 9/9 |
| T-88 | Solar 운영 provider | **done** | solarProvider·baseHttpProvider 공통화. json_object 채택. /health 버그 수정 |
| 가드 | 컬렉션-임베더 일치 | **done** | 메타 model·dim + drop/recreate. DIM=embed_dim(256→384) |
| T-83 | kg/save draft_id 영속 멱등 | **done** | dom:draftId 트리플. 재기동에도 중복 0. 지식 101건 |
| T-84 | Idempotency·Breaker 외부화 검토 | **done** | 아래 결정 |
| T-73 | unknown_concept 온톨로지 소속 접지 | **done** | **가드레일을 프롬프트 규율에서 분리**(결정론 접지). 프롬프트 완화 뒤에도 우회 9/9 안정(2R)·회귀 24 PASS |
| T-85 | 상위 온톨로지 승인 TTL 영속화 | todo | (T-73 뒤로 미룸 — admin 독립 기능, 리스크 낮음) |
| T-71 | LLM-as-Judge (Solar 실키) | todo | |
| T-72 | 실패 케이스 | todo | |
| T-80·81·82 | Docker×3·시드적재/캐시·CI | todo | |
| T-86 | BFF flaky 근절 | todo | |

## T-84 결정 — 상태 외부화 검토

- **저장 멱등**: **스토어에 영속(T-83)**. `kg/save` 는 `dom:draftId` 유니크로 재기동·다중전송·다중 인스턴스에도 중복 0. 해결됨.
- **BFF in-memory 상태 2종은 단일 인스턴스 가정**(명시):
  1. `extraction.ts` `savedDrafts` — 프로세스 메모리 **fast-path**. 소실돼도 정합성 backstop 은 스토어(T-83). 문제없음.
  2. `reliability.ts` `CircuitBreaker` — 프로세스별 실패 카운트. 재기동 시 closed 초기화. 단일 BFF 배포에서 정상.
- **결정**: 현재 배포 토폴로지는 **단일 BFF 인스턴스** → 외부화 불필요. 다중 인스턴스로 확장 시 Breaker 상태만 공유 스토어(Redis 등)로 외부화한다(멱등은 이미 스토어라 추가 작업 없음). 코드 주석에 가정 명시(reliability.ts·extraction.ts).

## 핵심 발견 (값을 치른 것)

- **solar-pro3 는 `json_schema strict` 로 추론 품질이 떨어진다**(정답 A→C, 추출 공집합) → `json_object`+프롬프트스키마.
- **`/health` 가 provider 를 오보**했다(별도 계산이 Solar 를 몰라 claude 로) — 실제 게이트웨이 선택 반영으로 수정.
- **가드레일이 LLM 추출 규율에 의존**한다 — 도메인 낱말 섞은 우회가 프롬프트 완화 시 샌다. 엄격 프롬프트로 9/9 유지. **결정론 접지는 T-73** 이 넣는다(그 후 프롬프트 완화로 in-domain 리콜 개선).
- solar-pro3 in-domain 간헐 공집합 추출 → 접지가 **안전하게 insufficient 로 fail-closed**(환각 아님).
