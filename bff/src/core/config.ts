/**
 * 설정 — 환경변수만이 진실원.
 * API 키는 프로세스 env 에서만 읽는다. 코드·.env·git·이미지·로그(마스킹)에 절대 두지 않는다.
 */
export const config = {
  port: Number(process.env.BFF_PORT ?? 4000),
  knowledgeUrl: process.env.KNOWLEDGE_URL ?? "http://localhost:8000",
  logLevel: process.env.LOG_LEVEL ?? "info",

  /**
   * MOCK 우선 — AI_MOCK_MODE=true(기본) 이거나 쓸 수 있는 provider 키가 하나도 없으면 mock.
   * 운영은 `.env` 에서 AI_MOCK_MODE=false + AI_PROVIDER=solar + Studio_API_Key 로 실 provider 사용.
   */
  aiMockMode:
    (process.env.AI_MOCK_MODE ?? "true") === "true" ||
    (!process.env.Studio_API_Key &&
      !process.env.UPSTAGE_API_KEY &&
      !process.env.ANTHROPIC_API_KEY &&
      !process.env.GOOGLE_AI_API_KEY),

  /** 운영 provider 선택 (mock|solar|claude|gemini). 미설정 시 자동 우선순위(solar→claude→gemini). */
  aiProvider: (process.env.AI_PROVIDER ?? "").toLowerCase(),

  anthropicApiKey: process.env.ANTHROPIC_API_KEY,
  googleAiApiKey: process.env.GOOGLE_AI_API_KEY,
  /** 앱 AI 기본 = Solar(Upstage, OpenAI 호환). 키 별칭 Studio_API_Key | UPSTAGE_API_KEY. */
  solarApiKey: process.env.Studio_API_Key ?? process.env.UPSTAGE_API_KEY,
  solarBaseUrl: process.env.SOLAR_BASE_URL ?? "https://api.upstage.ai/v1",
  solarModel: process.env.SOLAR_CHAT_MODEL ?? "solar-pro3",
  /** solar-pro3 reasoning_effort (미설정 시 미전송 → 모델 기본). */
  solarReasoningEffort: process.env.SOLAR_REASONING_EFFORT,

  /** 최신 모델 (claude-api 스킬 기준). Opus 4.8 은 temperature 를 받지 않으므로 structured output 로 결정론을 확보한다. */
  anthropicModel: process.env.ANTHROPIC_MODEL ?? "claude-opus-4-8",
  geminiModel: process.env.GOOGLE_AI_MODEL ?? "gemini-2.0-flash",

  /**
   * 지식서비스 mock 스위치. T-55(지식서비스) 가 동시 구현 중이라
   * 신설 엔드포인트가 아직 없을 수 있다. mock 이면 contracts/mocks 를 반환한다.
   * 기본: 키 없이(=mock AI) 돌 때는 지식도 mock 으로 선행. KNOWLEDGE_MOCK 로 강제 가능.
   */
  knowledgeMock:
    (process.env.KNOWLEDGE_MOCK ?? "").toLowerCase() === "true" ||
    ((process.env.KNOWLEDGE_MOCK ?? "") === "" &&
      (process.env.AI_MOCK_MODE ?? "true") === "true" &&
      !process.env.ANTHROPIC_API_KEY &&
      !process.env.GOOGLE_AI_API_KEY),

  /** 신뢰성 패턴 (interface_contracts.md §6) */
  timeouts: { llmMs: 30_000, knowledgeMs: 20_000, satisfyMs: 60_000 },
  retry: { attempts: 2, baseDelayMs: 250 },
  breaker: { failureThreshold: 5, openMs: 60_000 },
} as const;

/** 로그·에러 본문에서 키 형태를 지운다. */
export function maskSecrets(text: string): string {
  return text
    .replace(/(sk-[A-Za-z0-9_-]{4})[A-Za-z0-9_-]+/g, "$1***")
    .replace(/(AIza[A-Za-z0-9_-]{4})[A-Za-z0-9_-]+/g, "$1***")
    .replace(/(up[-_][A-Za-z0-9]{4})[A-Za-z0-9_-]+/gi, "$1***") // Upstage Solar 키
    .replace(/(Bearer\s+[A-Za-z0-9_-]{4})[A-Za-z0-9_.-]+/g, "$1***");
}
