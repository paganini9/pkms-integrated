# 참고 · Solar(Upstage) LLM provider 연동 (04 그래프·코어 소유)

> `LLM_PROVIDER=solar` 일 때 사용. OpenAI 호환 SDK(chat completions).
> **키는 .env(SOLAR_API_KEY)에서만 — 코드 하드코딩 금지.**

## 확정된 연동 패턴 (chat completions) ★우리 LLM 코어가 쓰는 것
- SDK: `openai` (>=1.81)
- base_url: `https://api.upstage.ai/v1`   ← chat completions (문서-에이전트의 /v2 와 다름)
- model: `solar-pro3`
- 키: `settings.solar_api_key`

```python
from openai import OpenAI
from app.core.config import settings

def _solar_client() -> OpenAI:
    return OpenAI(api_key=settings.solar_api_key, base_url="https://api.upstage.ai/v1")

# 비스트리밍 (분기·구조화 노드: intent_router, transition_analyzer 등)
resp = _solar_client().chat.completions.create(
    model="solar-pro3",
    messages=messages,              # [{"role": "...", "content": "..."}]
    # reasoning_effort="high",      # 분석 깊이 필요 시(분기/재현 중시 노드는 보수적으로)
    stream=False,
)
text = resp.choices[0].message.content

# 스트리밍 (briefing_synthesizer → API SSE token 이벤트로 흘리기)
stream = _solar_client().chat.completions.create(
    model="solar-pro3", messages=messages, stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        yield delta                 # SSE token 으로 전달
```

## LLM.generate() 계약 매핑
- `generate(messages, schema, temperature)` → Solar 경로는 위 chat.completions 로 구현.
- 분기·구조화 노드: `stream=False` + JSON 파싱. structured output(response_format=json_schema) 지원 여부는 Upstage 문서 확인, 미지원 시 프롬프트 강제 + 후처리로 dict 보장.
- 재현성(분기 노드): temperature 낮게(가능하면 0), `reasoning_effort` 남용 금지(결정성 우선). 합성 노드는 reasoning/stream 허용.
- claude 기본 ↔ solar 전환은 `LLM_PROVIDER` env 한 줄(provider 추상화 뒤).

## 구분 — 문서-에이전트 예시는 별도 용도
- `model="agt_..."` + `responses.create` + 파일 업로드 + 폴링 = Upstage **Agent**(문서처리, base_url `/v2`). MacroLens LLM 코어엔 불필요(향후 PDF 리서치 등에서만 검토).

## 체크
- `SOLAR_API_KEY` 가 `.env` 에 있고 커밋 안 됨. `openai>=1.81` requirements 포함.
