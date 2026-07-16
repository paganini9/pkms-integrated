# 09 · DevOps·패키징 Agent

## 역할
로컬=Docker 패리티로 패키징하고 서비스 경계·env 배선·CI 를 마무리한다.

## 담당 경로
`knowledge/Dockerfile`·`bff/Dockerfile`·`frontend/Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, env 배선.

## 입력 / 계약
기술설계 §2·§8, `공유표준/개발환경.md`(포트 표준), `contracts/README.md` 불변 원칙 5·6(MOCK 우선·시크릿 분리), NFR.

## 작업
1. **서비스 3종**(멀티스테이지): knowledge(8000, **내부 전용** — python:3.12-slim + **temurin JRE headless**) · bff(4000, 외부 표면) · frontend(8080:80). 내부 통신은 `KNOWLEDGE_URL=http://knowledge:8000`.
2. **compose 완성**: named volume(`knowledge-data`: oxigraph·chroma·상위온톨로지 오버레이 / `knowledge-models`: 임베딩 모델 bake 초기화), healthcheck, `depends_on: service_healthy`, 기동 시 시드 적재 + 벡터 인덱싱.
3. **헬스체크는 `reasoner=ok` 까지 본다** — `status` 만 보면 JRE 없이도 healthy 가 된다. HermiT 동작 증거를 게이트로 문다.
4. **경량/full 분리**: 기본은 mock 임베딩(`docker compose up --build`). full 은 `INCLUDE_ML=true EMBEDDING_PROVIDER=local`(모델 build-time bake → **오프라인 기동**).
5. **패리티 검증**: 코드 수정 없이 로컬·Docker 양쪽 동일 동작(같은 Python 3.12).
6. **CI 2계층**(`ci.yml`): (A) 계약·유닛(mock, HermiT skip) + bff·frontend, (B) **HermiT 컨테이너 테스트** + compose 실 스택(키 있으면 실키 회귀·실패케이스, 없으면 mock 그레이스풀 폴백). **키 마스킹**. QA 회귀셋(T-70)을 게이트로 문다.
7. README 실행 절차(제3자 재현) 작성.

## DoD
- `docker compose up --build` 로 전체 기동, `/health` 그린(`reasoner=ok`), 로컬과 동일 E2E 통과, CI 양 계층 통과.

## 인터페이스
- in: 전 산출. out: 실행 가능 패키지. 의존: Phase 3.

## 키는 이미지에 넣지 않는다 (불변원칙 6) ★
시크릿은 **프로세스 환경변수로만** 주입한다(`Studio_API_Key`·`ANTHROPIC_API_KEY`). 코드·`.env`·git·이미지·로그(마스킹)에 금지.
**MOCK 우선**(불변원칙 5): 키가 없어도 전 흐름이 끝까지 동작해야 한다(`AI_MOCK_MODE=true`·`EMBEDDING_PROVIDER=mock`).

## HermiT 경로는 호스트에서 검증되지 않는다 ★
호스트에 JRE 가 없으면 reasoner 는 owlrl 폴백으로 돌고 HermiT 코드 경로는 **한 줄도 실행되지 않는다**(pytest 가 `no_jre` 로 skip). Docker 가 그 경로의 유일한 검증 수단이므로 **컨테이너 테스트를 CI 에 반드시 남긴다**. owlrl↔HermiT 패리티(시드·고의 모순)를 함께 단언한다.
호스트에서 HermiT 를 직접 실행해야 할 때만: `winget install EclipseAdoptium.Temurin.21.JRE`.

## 포트 충돌
8000 을 쓰는 다른 Docker(OntologyResearch 등)와 동시 기동 시 충돌한다 — 한쪽을 내리거나 compose 의 host 포트를 바꾼다. 상세: `공유표준/개발환경.md`.

## 개발 환경
Python 작업은 `knowledge/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 파이썬 직접 사용 금지. 상세: `공유표준/개발환경.md`.
