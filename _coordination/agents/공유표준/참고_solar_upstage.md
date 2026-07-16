# 참고 · Solar(Upstage) LLM provider 연동 (05 백엔드·BFF 소유)

> `AI_PROVIDER=solar` 일 때 사용. **운영 기본 provider.** OpenAI 호환 chat completions.
> **키(`Studio_API_Key`)는 프로세스 env 에서만 — 코드·`.env`·이미지·로그 금지**(불변원칙 6).
> 구현 위치: `bff/src/services/ai/solarProvider.ts`(+ 공통 `baseHttpProvider.ts`). 근거: `docs/Solar-AI백엔드-통합가이드.md`.
> **LLM 호출은 BFF(Node)의 일이다** — 지식서비스(Python)는 LLM 을 호출하지 않는다(불변원칙 1·3).

## 확정된 연동 패턴 (chat completions)

- transport: **`fetch` 직접 호출**(레포 idiom — ClaudeProvider 도 fetch). OpenAI SDK 를 쓰지 않는다.
- base_url: `https://api.upstage.ai/v1` → `/chat/completions`  ← 문서-에이전트의 `/v2` 와 다름
- model: `solar-pro3` (`config.solarModel`) · 옵션 `reasoning_effort`(`config.solarReasoningEffort`)
- 키: `Studio_API_Key`(프로세스 env) → `authorization: Bearer …`

```ts
const body = {
  model: config.solarModel,
  messages: [{ role: "system", content: system }, { role: "user", content: user }],
  ...(config.solarReasoningEffort ? { reasoning_effort: config.solarReasoningEffort } : {}),
  ...(jsonMode ? { response_format: { type: "json_object" } } : {}),
};
await fetch(`${config.solarBaseUrl}/chat/completions`, {
  method: "POST",
  headers: { "content-type": "application/json", authorization: `Bearer ${apiKey}` },
  body: JSON.stringify(body),
});
```

## `json_schema` strict 를 쓰지 않는다 — 실측으로 배웠다 ★

가이드는 structured output 을 `response_format: json_schema(strict)` 로 안내하지만, **solar-pro3 에서는 구조 강제 디코딩이 추론을 눌러 품질을 떨어뜨린다**(분류 정답 A→C, 추출 공집합). 채택한 형태:

1. **`json_object` 모드 + 스키마를 프롬프트에** 실어 받고 JSON 파서로 파싱한다. 이것이 가이드가 말한 "json_schema 미지원 시 JSON프롬프트+파서 폴백"의 실제 형태다.
2. `json_object` 조차 `400`/`422` 로 거부되면 포맷 없이 프롬프트만으로 재시도한다.
3. 프롬프트·스키마·파싱은 `BaseHttpProvider` 공통이다 — **가드레일이 Claude 와 동일해야 한다**. provider 별로 갈리면 한쪽에서만 우회가 뚫린다.

## `AIProvider` 계약 매핑 (`contracts/interface_contracts.md` §3)

- `extract(text)` — structured output, temperature 0~0.2. 추출 초안·도메인 접지(CD-13)의 입력.
- `parseRequirements(text)` · `answer(question, sources)` — **`sources` 가 비면 throw**(CD-14, 검증 답변 전용).
- `llmOnlyAnswer(question)` — 무근거 단독 답변. **환각비교의 `llm_answer` 에만** 쓴다.
- 재현성: 판정에 닿는 경로는 temperature 낮게(가능하면 0), `reasoning_effort` 남용 금지. **판정 필드는 LLM 이 채우지 않는다**(불변원칙 3).
- provider 전환은 env 한 줄: `AI_PROVIDER`(+ 태스크별 `AI_AUTHORING_PROVIDER`·`AI_QA_PROVIDER`). 키가 없으면 gateway 가 **mock 으로 그레이스풀 폴백**(불변원칙 5).
- 호출은 Timeout·Retry·CircuitBreaker 로 감싼다(`reliability.ts`).

## 구분 — 문서-에이전트 예시는 별도 용도

- `model="agt_..."` + `responses.create` + 파일 업로드 + 폴링 = Upstage **Agent**(문서처리, base_url `/v2`). PKMS LLM 코어엔 불필요(향후 PDF 리서치 등에서만 검토).

## 체크

- `Studio_API_Key` 가 **호스트 env** 에 있고 코드·`.env`·이미지·로그에 없다. 키 없이도 mock 으로 전 흐름이 돈다.
- 실키 판정은 **실 스택**에서 한다(`KNOWLEDGE_MOCK=false`) — mock 통과는 게이트가 아니다.
