# Phase 3 이어가기 — 재설정된 진행계획 + 붙여넣기 프롬프트 (T-73 이후)

> 기준: `Phase3-킥오프-지시문.md`(v2)의 태스크 정의 + 이번 세션 산출(Docker/HermiT 검토, OOV 설계제안) 반영.
> 변경점: ① 남은 순서를 **Docker 먼저(롱폴·최고리스크 디리스킹)** 로 재설정, ② T-80/81/82 DoD를 Docker/HermiT 검토로 보강, ③ **T-89(OOV 슬라이스)를 포스트-g3 백로그로 파킹**(릴리스 비차단).

---

## 1. 현재 상태

- **완료·푸시(Phase 3)**: 배치계획 · T-87(inferred 엣지) · T-70(회귀셋+실스택러너) · T-88(Solar provider) · 가드(컬렉션-임베더 일치) · T-83(draft_id 멱등) · T-84(상태 외부화) · **T-73(결정론 접지)**.
- **남은 것**: T-85 · T-71 · T-72 · T-80/81/82 · T-86 · §5 게이트+Solar 실키 → 릴리스.
- **백로그(포스트-g3)**: T-89 저작 OOV 트리아지+SKOS 어휘층+제안 큐 MVP 슬라이스(근거 `docs/OOV-용어처리-온톨로지진화-설계제안.md`).

## 2. 재설정된 순서 (근거)

**Docker(T-80~82)가 롱폴이자 최고 리스크**다 — greenfield에 규모가 크고, 무엇보다 **HermiT 경로가 한 번도 실행된 적 없다**(`reasoner.py._consistency_hermit` = `pragma: no cover`, 호스트 no_jre). 미검증 경로는 런웨이 있을 때 깨야 한다. 그래서:

```
0. (선행) 허브 최신 지시문서 → repo docs/ 동기화 + develop push
1. T-80  Docker 스켈레톤 + HermiT 스모크 + owlrl↔HermiT 패리티   ← 리스크 먼저
2. T-85  상위 온톨로지 승인 TTL 영속화        ┐ (독립·빠름, 1과 병렬 가능)
3. T-71  LLM-as-Judge (Solar 실키) → T-72 실패케이스  ┘ (T-88·T-73 완료로 unblocked)
4. T-81  compose 완성(볼륨·healthcheck·시드적재·모델bake)
5. T-82  CI 2계층(mock 빠른 / 릴리스 스모크 full)  →  T-86 flaky 근절
6. §5 게이트 + 운영 provider(Solar) 실키 검증 → 릴리스_노트 + 태그 g3-release
```

트랙 병렬(소유 경로 무중복): [C]DevOps(T-80·81·82·86) · [B]04(T-85) · [A]08(T-71·72). 교차 의존은 T-81/82←T-80 뿐(T-70·T-88·T-73은 완료).

## 3. T-80/81/82 DoD 보강 (Docker/HermiT 검토 반영)

- **T-80** Dockerfile×3(**멀티스테이지**) + compose 스켈레톤. knowledge 이미지에 **temurin JRE headless**. 착수와 동시에:
  - **HermiT 스모크**: seed 온톨로지 `sync_reasoner_hermit` 일관성 + **고의 모순 온톨로지 clash 검출**(`engine="hermit"`) — 미검증 경로를 처음으로 실행·확인.
  - **owlrl(dev) ↔ HermiT(Docker) 패리티 테스트**: seed 일관성·분류가 두 리즈너에서 일치. (OWL RL은 불완전 — 불일치 시 prod 서프라이즈. satisfy subsumption·unknown_concept·영향분석이 여기 걸림.)
  - 이미지 경량(mock)/full(local ML) 을 **빌드아규먼트(`INCLUDE_ML`)** 로 분리.
- **T-81** compose 완성: `data/{oxigraph,chroma}`·**모델캐시 named volume**, **healthcheck**(knowledge `/health`가 Docker에서 `reasoner=ok` = JRE 동작 증거), `depends_on: service_healthy`, **시드 멱등 적재 + 벡터 초기 인덱싱**, **로컬 임베딩 모델 build-time bake**(오프라인 기동).
- **T-82** CI **2계층**: (a) 빠른 계약·유닛(mock, no JRE/torch) (b) **릴리스 스모크**(full 이미지·JRE·모델·Solar/Claude 키 — 없으면 mock 그레이스풀). **추론 의존 AC(일관성·분류)는 HermiT 컨테이너에서 1회**. `validate_contracts`+typecheck+회귀셋+실스택+Solar 스모크. 키 마스킹.
- **T-86** BFF flaky: **근본수정 또는 격리+출력강제보존+CI 결정론**(둘 중 하나로 닫아 릴리스 블로커화 방지). 임시 데이터 디렉터리 격리로 파일락 해소.

## 4. T-89 (OOV 슬라이스) — 포스트-g3 백로그

릴리스를 지연시키지 않도록 **릴리스 후**로 파킹(핵심가치지만 와이퍼 MVP 경계 밖일 수 있음). 착수 시: 어휘층(SKOS altLabel, 화이트리스트를 온톨로지 데이터로 이관) + OOV 트리아지 카드(매핑 제안 + 관리자 확장 제안 스텁 + provenance) + **접지 fail-closed 불변**. 상세 `docs/OOV-용어처리-온톨로지진화-설계제안.md`. 재현님이 Phase 3로 당길지 릴리스 후로 둘지 결정.

## 5. 붙여넣기 프롬프트 (오케스트레이터)

```
Phase 3 이어가기. 완료·푸시됨: 배치계획·T-87·T-70·T-88(Solar)·가드·T-83·T-84·T-73. 남은 것을 아래 순서/DoD로 진행한다.

선행: 허브 최신 지시문서(OOV-용어처리-온톨로지진화-설계제안·Phase3-이어가기-지시문·갱신된 Solar-AI백엔드-통합가이드)를 repo docs/로 동기화하고 develop push. task_board에 T-80/81/82 DoD를 아래로 보강하고 T-89를 백로그(포스트-g3)로 추가한 뒤 배치계획 보고 후 착수.

순서(트랙 병렬, 교차의존은 T-81/82←T-80 뿐):
1) [DevOps·롱폴·리스크먼저] T-80 Dockerfile×3(멀티스테이지)+compose 스켈레톤, knowledge 이미지에 temurin JRE headless. 착수와 동시에 HermiT 스모크(seed sync_reasoner_hermit 일관성 + 고의 모순 clash 검출 engine="hermit") + owlrl(dev)↔HermiT(Docker) 패리티 테스트(seed 일관성·분류 일치). 이미지 경량(mock)/full(local ML)은 빌드아규먼트 INCLUDE_ML로 분리.
2) [04] T-85 상위 온톨로지 승인 후 TTL 영속화(현재 승인 게이트까지만 → 재기동 후 유지).
3) [08] T-71 LLM-as-Judge(Solar 실키, 결정론 100%·미검증근거 0) → T-72 실패 케이스(타임아웃·range·수치누락·도메인밖·롤백; 도메인밖·롤백은 Solar 실키로도 1회).
4) T-81 compose 완성: data/{oxigraph,chroma}·모델캐시 named volume, healthcheck(knowledge /health reasoner:ok=JRE 증거), depends_on service_healthy, 시드 멱등적재+벡터 초기인덱싱, 로컬 임베딩 모델 build-time bake(오프라인 기동).
5) T-82 CI 2계층: (a) 빠른 계약·유닛(mock, no JRE/torch) (b) 릴리스 스모크(full 이미지·JRE·모델·Solar/Claude 키—없으면 mock 그레이스풀). 추론 의존 AC는 HermiT 컨테이너에서 1회. validate_contracts+typecheck+회귀셋+실스택+Solar 스모크, 키 마스킹. → T-86 BFF flaky(근본수정 또는 격리+출력강제보존+CI 결정론, 임시 데이터 디렉터리 격리).
6) §5 통합 게이트 전 항목 + 운영 provider(Solar) 실키 검증 통과 확인 → 릴리스_노트.md + 태그 g3-release.

원칙: 게이트는 실 스택·Solar 실키(mock·Claude 통과만으로 불충분). 결정론 경로에 "값 없으면 채우기" 금지. 레이어 분리·키 시스템 env·로그 마스킹. 각 단계 한글 커밋+push origin develop. 각 태스크 완료 시 결과 보고 후 다음으로.

백로그(릴리스 비차단): T-89 저작 OOV 트리아지+SKOS 어휘층+제안 큐 MVP 슬라이스(docs/OOV-용어처리-온톨로지진화-설계제안.md, 접지 fail-closed 불변). g3-release 후 착수 여부 결정.
```
