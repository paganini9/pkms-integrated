/**
 * ClaudeProvider — Anthropic Messages API (claude-api 스킬 기준). transport 만 담당한다.
 * 프롬프트·스키마·파싱은 BaseHttpProvider 공통(도메인-엄격 추출이 provider 간 갈리지 않게).
 * 최신 모델 `claude-opus-4-8`. Opus 4.8 은 temperature 를 받지 않으므로(400) structured output
 * (`output_config.format`)로 결정론을 확보한다. 키는 프로세스 env 에서만 읽고 로그에 남기지 않는다 (불변원칙 6).
 */
import { config } from "../../core/config.js";
import { AppError } from "../../core/errors.js";
import { BaseHttpProvider, type JsonSchema } from "./baseHttpProvider.js";

const API = "https://api.anthropic.com/v1/messages";

export class ClaudeProvider extends BaseHttpProvider {
  readonly name = "claude" as const;
  constructor(private readonly apiKey: string) {
    super();
  }

  protected async complete(system: string, user: string, schema?: JsonSchema): Promise<string> {
    const body: Record<string, unknown> = {
      model: config.anthropicModel,
      max_tokens: 4096,
      system,
      messages: [{ role: "user", content: user }],
    };
    if (schema) body.output_config = { format: { type: "json_schema", schema } };
    const res = await fetch(API, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": this.apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      // 내부 원인만; 4xx httpStatus 를 보존해 재시도 판단에 쓴다.
      throw new AppError("LLM_ERROR", "AI 응답에 실패했습니다. 다시 시도해 주세요.", res.status, `claude ${res.status}`);
    }
    const data = (await res.json()) as { content?: Array<{ type: string; text?: string }> };
    return (data.content ?? []).filter((b) => b.type === "text").map((b) => b.text ?? "").join("");
  }
}
