# PKMS × Solar(Upstage) — 앱 AI 백엔드 통합 가이드

> 작성일 2026-07-09 · 갱신 2026-07-10(임베딩=로컬 MiniLM 384 확정, 코드 정합) · 대상: dev_team(개발 시 준수). PKMS **앱 런타임**의 AI 백엔드를 Solar(Upstage)로 구현.
> ⚠️ **Claude Code(개발 도구)는 별개**다. `claude` CLI는 계속 Claude 인증을 쓰며 Solar로 대체 불가. 이 가이드는 **앱이 호출하는 AI**(추출·Q&A·임베딩)에만 적용된다.

---

## 0. 원칙

- 앱 AI 백엔드 = **Solar(Upstage), OpenAI 호환** API. Node·Python 모두 `openai` SDK에 `base_url`만 바꿔 사용.
- **chat provider = Solar**, `AI_MOCK_MODE=true`면 키 없이 Mock으로 전 흐름 동작(개발·CI). Claude/Gemini는 대체 provider로 남겨 인터페이스 유지.
- **생성기–검증기 안전망**: LLM 출력은 어차피 OWL/SHACL/satisfy가 결정론적으로 검증하므로, provider 교체 리스크는 낮다.
- **AWS×Upstage 초기 프로그램 커버리지**: 이 프로그램은 **Solar-Pro(=solar-pro3, chat)와 Document-Parse를 무료**(~2027-03-31)로 준다. 우리 주 LLM 용도(추출·RB·규칙·Q&A)는 여기에 **포함**. **임베딩(solar-embedding-2)은 목록 밖(무료 아님)** → **결정: 임베딩 = 로컬**(무료·오프라인), **기본 모델 MiniLM 다국어(384)**. chat=Solar-Pro, embedding=local. (Phase 1 코드가 이미 로컬 임베딩으로 구현됨 — §5 구현 상태.)

## 1. 키 · 보안

- `Studio_API_Key` = **Windows 시스템 환경변수**. 코드·`.env`·git·이미지에 넣지 않음, 로그 마스킹.
- Node: `process.env.Studio_API_Key` · Python: `os.environ["Studio_API_Key"]`. (별칭 `UPSTAGE_API_KEY`도 허용 가능.)

## 2. 어디에 붙나 (아키텍처)

| 위치 | 용도 | Solar 사용 |
|------|------|-----------|
| **BFF(Node) AI Gateway** | 개념·관계 추출 · RB 파싱 · 규칙 추출 · Q&A 초안 · SSE | **chat**(solar-pro3) |
| **지식·추론 서비스(Python) RAG** | 지식문장 색인·검색 | **임베딩 = 로컬**(기본), Solar 임베딩은 옵션 |

## 3. 엔드포인트 · 모델 매핑

| 용도 | base_url | model | 비고 |
|------|----------|-------|------|
| Chat / 생성 / Q&A | `https://api.upstage.ai/v1` | `solar-pro3` | `reasoning_effort`, `stream`, (구조화는 `response_format`) |
| 임베딩(**기본=로컬**, §5) | 로컬 | `MiniLM 다국어`(384, 기본) · `bge-m3`(1024)/`ko-sroberta`(768) 대안 | 무료·오프라인 |
| 임베딩(옵션=Solar) | `/v1` | `solar-embedding-2-passage`/`-query`(1024) | 프로그램 무료 아님 |
| (향후) 정보추출 | `/v1/information-extraction` | `information-extract` | 문서/이미지→스키마 |
| (향후) 문서분류 | `/v1/document-classification` | `document-classify` | |
| (향후) 문서파싱(OCR) | `/v1/document-digitization` | `document-parse` | |
| (향후) 파일 업로드 | `/v2` | files API | Agents/파일 |

> **주의 1 — 기능별 base_url이 다르다**(chat은 `/v1`, 정보추출은 `/v1/information-extraction` …). provider가 기능에 따라 라우팅.
> **주의 2 — 로컬 임베딩은 대칭**: 기본 MiniLM은 색인·질의에 **같은 모델**을 쓴다(§5.1). Solar 임베딩(옵션)만 passage/query 비대칭이며 섞으면 검색 품질이 무너진다.
> **주의 3 — 차원·정규화**: 컬렉션 `distance=cosine`, 정규화 벡터(크기 1)라 코사인=내적. **차원은 모델 차원**(MiniLM=384 / bge-m3=1024 / ko-sroberta=768 / Solar=1024). **모델(차원) 변경 시 Chroma 컬렉션 재생성·재인덱싱 필수.**
> **주의 4 — Solar 옵션 사용 시 alias vs v2**: Upstage는 별칭 `embedding-query`/`embedding-passage` 사용을 권장하나 현재 이 별칭은 **v1-large(4096, 서비스종료 2026-08-31)** 를 가리킨다. **v2(1024·8k, 2026-07-20까지 무료)** 는 아직 별칭이 없어 풀네임 사용.

## 4. BFF(Node) — Solar chat provider (스케치)

```ts
// bff/src/services/ai/providers/solar.ts
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.Studio_API_Key,                       // 시스템 env
  baseURL: process.env.SOLAR_BASE_URL ?? "https://api.upstage.ai/v1",
});
const CHAT = process.env.SOLAR_CHAT_MODEL ?? "solar-pro3";

// SmartInput 추출 스트리밍(SSE) 용
export async function* streamChat(messages: any[]) {
  const stream = await client.chat.completions.create({
    model: CHAT, messages, stream: true,
    // @ts-expect-error Upstage 확장 파라미터
    reasoning_effort: "medium",
  });
  for await (const c of stream) {
    const d = c.choices[0]?.delta?.content;
    if (d) yield d;
  }
}

// 개념·관계 추출 / RB 파싱 / 규칙 추출 — 구조화 출력
export async function extractStructured(prompt: string, schema: object) {
  const res = await client.chat.completions.create({
    model: CHAT,
    messages: [{ role: "user", content: prompt }],
    response_format: { type: "json_schema",
      json_schema: { name: "extraction", schema } },   // ※ solar-pro3 strict 지원 확인
  });
  return JSON.parse(res.choices[0].message.content!);
}
```

- Strategy 패턴에 `'solar'` provider를 **chat 기본**으로 등록, `AI_MOCK_MODE`면 Mock. Claude/Gemini는 대체.

## 5. 지식서비스(Python) — 임베딩 (RAG)

> **확정: 로컬 임베딩(sentence-transformers)** — 프로그램이 임베딩을 무료로 주지 않으므로 **API·비용 0의 로컬**을 채택. **기본 모델 = MiniLM 다국어(384)**. Solar 임베딩은 옵션으로 보존.
>
> **구현 상태(Phase 1)**: `knowledge/rag/embedder.py`에 `MockEmbedder`+`StEmbedder`로 **이미 구현**됨(MOCK-first). 코드의 설정명은 `EMBEDDING_MODE(mock|st)`였고 → 이 가이드 표기 **`EMBEDDING_PROVIDER(mock|local|solar)`로 통일**(리네임: [임베딩-로컬-전환-지침.md]). 개발 기본값은 `mock`(무의존 동작), 실임베딩은 `local`(=StEmbedder, `requirements-ml.txt` 필요).

### 5.1 로컬 임베딩 (기본, `EMBEDDING_PROVIDER=local`)
```python
# knowledge/rag/embedder.py 의 StEmbedder 와 동일한 취지 (참고용 스케치)
import os
from sentence_transformers import SentenceTransformer
_m = SentenceTransformer(os.getenv("LOCAL_EMBED_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))  # 기본 384. 대안: BAAI/bge-m3(1024)·jhgan/ko-sroberta-multitask(768)
def embed_passages(texts): return _m.encode(texts, normalize_embeddings=True).tolist()
def embed_query(text):     return _m.encode(text,  normalize_embeddings=True).tolist()
```
- **대칭 모델**(색인·질의 동일 모델), `normalize_embeddings=True` → 코사인=내적. **차원=모델 차원**(MiniLM=384, bge-m3=1024, ko-sroberta=768) → Chroma 컬렉션 차원을 맞춤. **모델(차원) 변경 시 컬렉션 재생성·재인덱싱 필수**(mock 256 ↔ MiniLM 384 등 차원이 달라 섞을 수 없음).
- 첫 실행 시 모델 다운로드(이후 오프라인). 소량 코퍼스라 CPU로 충분. 의존성 `sentence-transformers`(+torch)는 `knowledge/requirements-ml.txt`(선택)에 — 없으면 `mock`로 폴백.
- 코퍼스가 와이퍼 6문장+소량이라 **경량 다국어 MiniLM(384)** 이 기본으로 충분(빠름·~120MB). 대규모·장문 검색이 필요해지면 bge-m3(1024, ~2.2GB)로 상향, 순한국어 위주면 ko-sroberta(768).

### 5.2 Solar 임베딩 (옵션, `EMBEDDING_PROVIDER=solar`)
```python
# knowledge/rag/embeddings_solar.py (옵션 — 현재 미구현, 붙일 때 참고)
import os
from openai import OpenAI

_client = OpenAI(api_key=os.environ["Studio_API_Key"],
                 base_url=os.getenv("SOLAR_BASE_URL", "https://api.upstage.ai/v1"))
PASSAGE = os.getenv("SOLAR_EMBED_PASSAGE_MODEL", "solar-embedding-2-passage")
QUERY   = os.getenv("SOLAR_EMBED_QUERY_MODEL",   "solar-embedding-2-query")

def embed_passages(texts: list[str]) -> list[list[float]]:   # 지식문장 색인 시
    r = _client.embeddings.create(input=texts, model=PASSAGE)
    return [d.embedding for d in r.data]

def embed_query(text: str) -> list[float]:                    # 검색 질의 시
    return _client.embeddings.create(input=text, model=QUERY).data[0].embedding
```

- Chroma upsert 시 `embed_passages`, 검색 시 `embed_query`. 컬렉션 차원 **1024**, distance=`cosine`(정규화 벡터). 배치 한도 ≤100 텍스트·204,800 토큰 → 초과 시 분할.
- **임베딩 provider 선택**(`EMBEDDING_PROVIDER`): `mock`(개발 기본, 무의존 해시벡터) / `local`(sentence-transformers, 기본 MiniLM 384 — API·비용 0, 오프라인, `requirements-ml.txt` 필요) / `solar`(옵션, Upstage; 프로그램 무료 아님, 미구현). **chat은 Solar-Pro(프로그램 무료) 유지**, 임베딩만 상황따라 스왑 — `encode`(또는 `embed_passages`/`embed_query`) 인터페이스는 동일. (`local`·모델 변경 시 컬렉션 차원을 해당 모델 차원으로 재생성.)
- **MOCK 폴백**: 키·패키지 없거나 `AI_MOCK_MODE`면 결정론적 더미 임베딩(해시 기반 고정 벡터, 256차원)으로 흐름만 검증.

## 6. 구조화 출력(추출·RB·규칙)

- `solar-pro3` + `response_format: json_schema`로 개념/관계·RB 절·DesignRule을 JSON으로. **strict 지원 여부는 콘솔에서 확인**하고, 미지원 시 "JSON만 출력" 프롬프트 + 파서 검증으로 대체.
- 문서/이미지 기반 추출이 필요해지면 `information-extract`(정보추출) 사용(현재 MVP 비목표, 향후 확장).
- 어떤 경로든 **최종 판정은 OWL/SHACL/satisfy** — 추출이 틀려도 명세가 거른다.

## 7. 환경 · 설정 (`.env.example` 등)

```
# 키는 시스템 환경변수(setx)로: Studio_API_Key  (여기에 넣지 않음)
AI_PROVIDER=solar                # chat = Solar-Pro (프로그램 무료)
EMBEDDING_PROVIDER=mock          # 개발 기본(무의존). 실임베딩=local(requirements-ml.txt) | 옵션 solar
AI_MOCK_MODE=true
SOLAR_BASE_URL=https://api.upstage.ai/v1
SOLAR_CHAT_MODEL=solar-pro3
# 로컬 임베딩(기본 모델). EMBEDDING_PROVIDER=local 일 때 사용
LOCAL_EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2  # 대안 BAAI/bge-m3·jhgan/ko-sroberta-multitask
EMBED_DIM=384                    # MiniLM=384, bge-m3=1024, ko-sroberta=768
# Solar 임베딩(옵션, EMBEDDING_PROVIDER=solar 일 때만)
SOLAR_EMBED_QUERY_MODEL=solar-embedding-2-query
SOLAR_EMBED_PASSAGE_MODEL=solar-embedding-2-passage
```

## 8. 검증 (스모크 · 회귀)

- **MOCK**: 키 없이 추출→검증→satisfy→Q&A 전 흐름 통과(기존 DoD).
- **로컬 임베딩 스모크**(키 불요): `EMBEDDING_PROVIDER=local`에서 벡터 길이 = `EMBED_DIM`(384), 첫 로드 후 오프라인 동작. 모델 전환 시 컬렉션 재인덱싱 확인.
- **Solar chat 스모크**(키 있을 때): chat "hi" 응답 + 추출 스키마 1건 유효 JSON.
- **회귀셋 추가**: 임베딩 차원 케이스, 추출 스키마 준수 케이스.

## 9. dev_team 반영 지점

- **03 RAG·지식**: **로컬 임베딩**(`EMBEDDING_PROVIDER=local`, 기본 MiniLM 384) + MOCK 폴백 — **Phase 1에 이미 구현**(`embedder.py` mock|local). Solar 임베딩은 옵션. 모델 변경 시 컬렉션 재인덱싱.
- **05 백엔드·API(AI Gateway)**: Solar chat provider 기본 등록 + SSE + 구조화 출력.
- **개발 지시(킥오프)에 포함**: "앱 AI 백엔드는 chat=Solar(Upstage)·임베딩=로컬. 이 가이드(`docs/Solar-AI백엔드-통합가이드.md`)를 준수. Claude Code 자체 인증과는 무관."

## 10. 확인 필요 (2차)

1. ✅ **확정**: (Solar 옵션 사용 시) `solar-embedding-2-query`/`-passage`, **1024차원**, 정규화 벡터, 8k 컨텍스트, 배치 ≤100/204,800토큰. v2 **무료 2026-07-20까지**. v1-large 별칭 `embedding-*`는 4096·**2026-08-31 종료**.
2. `solar-pro3`의 **`response_format: json_schema` strict** 지원 범위(미확정 → "JSON만 출력" 프롬프트+파서 폴백).
3. **레이트리밋**: chat RPM 100 / TPM 300,000 — 다중에이전트·대량 추출 시 스로틀·배치·캐시 설계.
4. ✅ **결정**: 임베딩 = **로컬 sentence-transformers**, 기본 **MiniLM 다국어(384)**(대안 bge-m3 1024·ko-sroberta 768) — 프로그램이 임베딩 무료 미포함. 설정명 `EMBEDDING_PROVIDER`(mock|local|solar), 개발 기본 `mock`. Phase 1 코드에 이미 구현(리네임만 반영). chat(Solar-Pro)·Document-Parse는 프로그램 무료(~2027-03-31).

Sources: Upstage 제공 샘플 코드(사용자), [Upstage Console — Models](https://console.upstage.ai/docs/models), [Qdrant — Upstage embeddings (query/passage, dim 4096)](https://qdrant.tech/documentation/embeddings/upstage/)
