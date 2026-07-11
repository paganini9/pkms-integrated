/**
 * SolarProvider — Upstage Solar (OpenAI 호환) transport (T-88). **운영 기본 provider.**
 *
 * 근거: docs/Solar-AI백엔드-통합가이드.md. `https://api.upstage.ai/v1/chat/completions`,
 * 모델 `solar-pro3`, `reasoning_effort`, structured output = `response_format: json_schema(strict)`.
 * OpenAI SDK 대신 fetch 로 직접 호출한다(레포 idiom = ClaudeProvider 도 fetch). 기능 동일.
 *
 * **json_schema strict 미지원 폴백**: 400/422 면 스키마를 프롬프트에 실어 재요청하고 JSON 파서로 받는다.
 * 프롬프트·스키마·파싱은 BaseHttpProvider 공통(가드레일이 Claude 와 동일해야 한다).
 * 키(`Studio_API_Key`)는 프로세스 env 에서만 읽고 로그에 남기지 않는다 (불변원칙 6).
 */
import { config } from "../../core/config.js";
import { AppError } from "../../core/errors.js";
import { BaseHttpProvider, type JsonSchema } from "./baseHttpProvider.js";

interface ChatChoice {
  message?: { content?: string };
}

export class SolarProvider extends BaseHttpProvider {
  readonly name = "solar" as const;
  constructor(private readonly apiKey: string) {
    super();
  }

  private async post(system: string, user: string, jsonMode: boolean): Promise<Response> {
    const body: Record<string, unknown> = {
      model: config.solarModel,
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
    };
    if (config.solarReasoningEffort) body.reasoning_effort = config.solarReasoningEffort;
    if (jsonMode) body.response_format = { type: "json_object" };
    return fetch(`${config.solarBaseUrl}/chat/completions`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${this.apiKey}` },
      body: JSON.stringify(body),
    });
  }

  private static content(data: unknown): string {
    const choices = (data as { choices?: ChatChoice[] }).choices ?? [];
    return choices.map((c) => c.message?.content ?? "").join("");
  }

  protected async complete(system: string, user: string, schema?: JsonSchema): Promise<string> {
    // solar-pro3 관측: `json_schema strict` 는 구조 강제 디코딩이 추론을 눌러 분류·추출 품질을
    // 떨어뜨린다(정답 A→C, 추출 공집합). → **json_object 모드 + 스키마를 프롬프트에** 실어 받는다.
    // 이것이 가이드가 말한 "json_schema 미지원 시 JSON프롬프트+파서 폴백"의 실제 형태다.
    const sys = schema
      ? `${system}\n\n반드시 아래 JSON 스키마에 맞는 **JSON 객체만** 출력하라(설명·코드펜스 금지):\n${JSON.stringify(schema)}`
      : system;

    let res = await this.post(sys, user, schema !== undefined);
    // json_object 조차 거부(400/422)하면 포맷 없이 프롬프트만으로 재시도.
    if (!res.ok && schema && (res.status === 400 || res.status === 422)) {
      res = await this.post(sys, user, false);
    }
    if (!res.ok) {
      throw new AppError("LLM_ERROR", "AI 응답에 실패했습니다. 다시 시도해 주세요.", res.status, `solar ${res.status}`);
    }
    return SolarProvider.content(await res.json());
  }
}
