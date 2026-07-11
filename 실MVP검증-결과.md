# 실 MVP 검증 결과 (g3-release 직후)

> 목적: **게이트 아님 — 관찰·확신 + T-89 스코핑.** full(ML) 로컬 임베딩 이미지가 미빌드라 실 RAG 리콜이
> 미검증이던 것을, **Solar chat + 로컬 MiniLM** 로 실제 한 번 돌려 관찰한다.
> 스택: frontend + bff(Solar solar-pro3) + knowledge(temurin JRE + local MiniLM 384). 2026-07-11.

## 1. full(ML) 이미지 빌드 — ✅ 실제로 됨(첫 빌드)

- `INCLUDE_ML=true` → **torch 2.13.0 + sentence-transformers 3.3.1 + transformers** 설치 성공(+CUDA 휠).
- **MiniLM(paraphrase-multilingual-MiniLM-L12-v2) build-time bake** 성공(SentenceTransformer 다운로드 26s → `/models`).
- **오프라인 기동 finding+fix**: `--network none` 에서 huggingface_hub 이 hub 로 HEAD(업데이트 확인) 시도 → 실패 재시도로 지연/경고.
  → **`HF_HUB_OFFLINE=1`·`TRANSFORMERS_OFFLINE=1`** 추가(이 브랜치). 재검증: 네트워크 없이 깨끗이 기동·인덱싱(경고 0).

## 2. 스택 기동 — ✅

- compose up: knowledge **Healthy**(healthcheck reasoner=ok=JRE) → bff(depends_on service_healthy) → frontend(HTTP 200).
- knowledge 로그: `embedding_provider=local reasoner=ok` · 시드 322 트리플 · **벡터 초기 인덱싱 6 문장**(실 MiniLM 384-dim).
- bff `/api/v1/health`: `llm_provider=solar` · knowledge.reasoner=ok.

## 3. 자동 스모크 (실 API, Solar + local) — 회귀 24/24 · 우회 9/9

- 전체 회귀셋(SC-1 추출·SC-2 satisfy·SC-3 qa·거버넌스·규칙) **24 PASS·0 FAIL**(1 SKIP meta).
- **`rag-verified-only` PASS** — mock 임베딩 한계였던 항목이 local 에선 라우팅·통과(개선).
- **가드레일 우회 8종 + qa-C = 9/9 차단 유지**(local 임베딩에서도).

### SC-2 satisfy (판정·근거·대안) — ✅ 정확
- BAD(고무600/8N/simple/중형SUV): `satisfies=False` · `violations=[S1,S3,S4,S6]` · **대안**=[재질→실리콘(S2)·길이→안전길이 이내(S5)·스프링→≥10N·암형상→complex].
- GOOD(실리콘550/12N/complex/세단): `satisfies=True` · `violations=[]`.

### SC-3 자유질의 + 환각비교 — ⚠️ 관찰(아래 §5)
- **환각비교 토글 동작**: 검증측은 "명세 근거 없음"(fail-closed), llm_only 는 Solar 일반답변(참고용) 생성 → **분리 정상**.
- 단, in-domain 자유질의가 **접지에서 과차단**됨(§5).

## 4. real(local) vs mock 임베딩 리콜 대조

같은 6문장을 각각 인덱싱, 정답 문장의 검색 랭크·유사도(0~1):

| 질의(의역) | local(MiniLM 384) | mock(해시 384) |
|---|---|---|
| 저온에서 블레이드가 시끄러운 원인은? | **rank 1** (S1, **0.621**) | rank 2 (S1, 0.153) |
| 떨림을 줄이려면 길이를 어떻게? | rank 2 (S3, 0.337) | rank 1 (S5, 0.130) |
| 소음을 잡아주는 재질은? | rank 2 (S2, 0.231) | rank 1 (S2, 0.192) |

- 두 질의는 시드와 일부 낱말이 겹쳐(저온·소음·떨림·재질) mock 도 정답을 잡았다 — **완전 비겹침 의역은 아니었다**.
- **핵심 신호는 유사도 점수**: local 0.62 vs mock 0.15(같은 S1). local 은 의미적 확신이 높고, mock 은 표층 겹침 의존(점수 낮음). 표층이 완전히 갈리는 의역에선 mock 이 놓칠 구간.

## 5. 실 스택 서프라이즈 (값)

1. **[테스트 아티팩트] bash-curl 한글 깨짐** — 직접 curl 로 보낸 `categories:["소음","떨림"]` 이 셸 인코딩으로 깨져(`applied_categories=['?']`) satisfy 가 규칙 미적용 → 헛-True. **httpx 러너(UTF-8)는 정상**(sat-bad=False). → 한글 payload 는 러너로 검증할 것.
2. **[진짜 발견 · T-89 직결] 자유질의 RAG 과차단** — Solar 추출이 **어휘 변형·잡음**을 낸다:
   - "겨울에 고무 블레이드…" → 추출 `[고무, **겨울**, 소음]` → **"겨울"(≠"겨울철")** unknown → 접지 차단.
   - "소음을 잡아주는 재질은?" → 추출 `[소음, **재질**, 잡아주는]` → **"재질"(총칭)·"잡아주는"(동사조각)** unknown → 접지 차단.
   - T-73 의 엄격 소속판정(CD-13 "미지 1건→insufficient")이 안전하게 fail-closed 하지만, **정상 in-domain 질의까지 막는다**.
   - **로컬 임베딩은 리콜을 개선하지만, 접지 게이트가 검색 이전에 막아 자유질의에선 임베딩 이득이 안 닿는다.** 병목은 임베딩이 아니라 **어휘/접지**다.
3. **SC-1 추출 품질** — Solar 가 "고무 블레이드"를 **복합어 한 개념**으로 뽑거나 관계를 누락. 저장은 되지만 파생 약함.
4. **llm_only 프롬프트 반향(간헐)** — 초기 curl 에서 llm_only 가 시스템 지시문을 영어로 반향한 케이스 관측(httpx 재현 시엔 정상 일반답변). solar-pro3 변동성.

## 6. 환각비교 관찰

- 검증측(온톨로지)과 llm_only(Solar 일반지식)가 **타입으로 분리**되어 나란히 반환됨(CD-14). 검증측이 근거 없으면 "명세 근거 없음", llm_only 는 계속 생성 → UI 환각비교 토글에 그대로 실린다. (스크린샷 3화면은 재현님 수동.)

## 7. T-89 스코핑 결론 (이 검증이 정한 것)

실 MVP 는 **구조화 경로(satisfy·검증·저장·거버넌스)와 안전(우회 9/9)은 견고**하다. 반면 **자유질의 RAG 는
"어휘/접지" 병목**이 실측으로 드러났다 — Solar 실LLM 이 내는 라벨 변형("겨울"·"재질")·복합어·동사조각을
엄격 소속판정이 과차단한다. **T-89(OOV 트리아지 + SKOS 어휘층 + 제안 큐)가 정확히 이 지점**이다:

- **SKOS altLabel 어휘층**: `_EXTRA_DOMAIN_VOCAB` 하드셋을 온톨로지 데이터(altLabel)로 이관 — "겨울"→Winter, "재질"→Material 총칭, 복합어("고무 블레이드")→부분매핑. **접지 fail-closed 불변**(모르는 건 여전히 막되, 알려진 변형은 통과).
- **OOV 트리아지 카드**: 진짜 미지(자전거·귀마개) vs 어휘변형·잡음(겨울·잡아주는)을 관리자에게 분리 제시 + 확장 제안.
- 로컬 임베딩(이 검증으로 유효 확인)은 어휘/접지가 열려야 자유질의에서 이득이 닿는다 → **T-89 와 함께 가야 값이 산다**.

**권고**: T-89 를 포스트-g3 백로그에서 **다음 우선**으로. 릴리스(g3)는 유효, 자유질의 품질은 T-89 가 연다.
