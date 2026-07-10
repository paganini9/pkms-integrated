/**
 * ClaudeProvider — Anthropic Messages API (claude-api 스킬 기준).
 * 최신 모델 `claude-opus-4-8`. Opus 4.8 은 temperature 를 받지 않으므로(400)
 * structured output(`output_config.format`)로 결정론을 확보한다.
 * 키는 프로세스 env 에서만 읽고 코드·로그에 남기지 않는다 (불변원칙 6).
 */
import { config } from "../../core/config.js";
import { AppError } from "../../core/errors.js";
import {
  CONCEPT_TYPES, EmptyContextError, PREDICATES,
  type AIProvider, type Concept, type ExtractionEvent, type Relation,
  type RequirementDraft, type Source,
} from "./types.js";

const API = "https://api.anthropic.com/v1/messages";

interface JsonSchema {
  type: "object";
  properties: Record<string, unknown>;
  required: string[];
  additionalProperties: false;
}

async function callClaude(
  apiKey: string,
  system: string,
  user: string,
  schema?: JsonSchema,
): Promise<string> {
  const body: Record<string, unknown> = {
    model: config.anthropicModel,
    max_tokens: 4096,
    system,
    messages: [{ role: "user", content: user }],
  };
  if (schema) {
    body.output_config = { format: { type: "json_schema", schema } };
  }
  const res = await fetch(API, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // 내부 원인만; 응답 본문은 로그로. 4xx httpStatus 를 보존해 재시도 판단에 쓴다.
    throw new AppError("LLM_ERROR", "AI 응답에 실패했습니다. 다시 시도해 주세요.", res.status, `claude ${res.status}`);
  }
  const data = (await res.json()) as { content?: Array<{ type: string; text?: string }> };
  const text = (data.content ?? []).filter((b) => b.type === "text").map((b) => b.text ?? "").join("");
  return text;
}

const EXTRACT_SCHEMA: JsonSchema = {
  type: "object",
  properties: {
    concepts: {
      type: "array",
      items: {
        type: "object",
        properties: {
          label: { type: "string" },
          type: { type: "string", enum: [...CONCEPT_TYPES] },
        },
        required: ["label", "type"],
        additionalProperties: false,
      },
    },
    relations: {
      type: "array",
      items: {
        type: "object",
        properties: {
          subject: { type: "string" },
          predicate: { type: "string", enum: [...PREDICATES] },
          object: { type: "string" },
          evidence: { type: "string" },
        },
        required: ["subject", "predicate", "object"],
        additionalProperties: false,
      },
    },
  },
  required: ["concepts", "relations"],
  additionalProperties: false,
};

const LAYER_SCHEMA: JsonSchema = {
  type: "object",
  properties: { layer: { type: "string", enum: ["A", "B", "C"] } },
  required: ["layer"],
  additionalProperties: false,
};

export class ClaudeProvider implements AIProvider {
  readonly name = "claude" as const;
  constructor(private readonly apiKey: string) {}

  async *extract(text: string): AsyncIterable<ExtractionEvent> {
    const raw = await callClaude(
      this.apiKey,
      "너는 **와이퍼 블레이드 도메인** 전용 지식 추출기다. 이 도메인의 개념만 뽑는다: " +
        "블레이드 재질(고무·실리콘 등), 차종(중형 SUV·소형 세단), 와이퍼 부품(암·스프링), " +
        "증상(소음·끝단 떨림), 환경(겨울철 저온), 관련 속성/거동. " +
        "**입력이 다른 도메인(타이어·엔진·자전거·노트북·일반 윤활유 등)이면 그 개념을 추출하지 마라.** " +
        "와이퍼 도메인 개념이 하나도 없으면 concepts 와 relations 를 **빈 배열**로 반환한다. " +
        "type·predicate 는 주어진 열거형만. 판정하지 말고 추출만 한다.",
      text,
      EXTRACT_SCHEMA,
    );
    let parsed: { concepts?: Concept[]; relations?: Relation[] };
    try {
      parsed = JSON.parse(raw);
    } catch {
      throw new AppError("LLM_ERROR", "AI 응답에 실패했습니다.", 502, "claude extract: JSON parse fail");
    }
    yield { kind: "status", stage: "extract", msg: "개념 추출 중" };
    for (const c of parsed.concepts ?? []) {
      if (CONCEPT_TYPES.has(c.type)) yield { kind: "concept", concept: { label: c.label, type: c.type } };
    }
    for (const r of parsed.relations ?? []) {
      if (PREDICATES.has(r.predicate)) {
        const relation: Relation = { subject: r.subject, predicate: r.predicate, object: r.object };
        if (r.evidence !== undefined) relation.evidence = r.evidence;
        yield { kind: "relation", relation };
      }
    }
  }

  async parseRequirements(text: string): Promise<RequirementDraft[]> {
    const schema: JsonSchema = {
      type: "object",
      properties: {
        requirements: {
          type: "array",
          items: {
            type: "object",
            properties: { forbids_symptom: { type: "string" }, label: { type: "string" } },
            required: ["forbids_symptom", "label"],
            additionalProperties: false,
          },
        },
      },
      required: ["requirements"],
      additionalProperties: false,
    };
    const raw = await callClaude(
      this.apiKey,
      "너는 요구사항 파서다. 자연어 요구를 '금지 증상' 단위로 분해해라. 존재하지 않는 증상도 추정해 실어라(존재 검증은 뒤 단계가 한다).",
      text,
      schema,
    );
    try {
      return (JSON.parse(raw).requirements ?? []) as RequirementDraft[];
    } catch {
      throw new AppError("LLM_ERROR", "AI 응답에 실패했습니다.", 502, "claude parseRequirements: JSON parse fail");
    }
  }

  async answer(question: string, context: Source[]): Promise<string> {
    if (context.length === 0) throw new EmptyContextError(); // CD-14: 검증 답변은 근거 없이 만들지 않는다.
    const ctx = "다음 검증된 근거만 사용해 답하라:\n" + context.map((s) => `- [${s.sentence ?? s.rule}] ${s.text ?? ""}`).join("\n");
    return callClaude(
      this.apiKey,
      "너는 와이퍼 설계 Q&A 답변기다. 판정 근거는 이미 결정론 엔진이 정했다. 주어진 근거로만 한국어 답변을 작성한다. 근거에 없는 내용은 덧붙이지 않는다.",
      `질문: ${question}\n\n${ctx}`,
    );
  }

  async llmOnlyAnswer(question: string): Promise<string> {
    // CD-14: 환각비교 전용. verified_answer 에 절대 쓰지 않는다.
    return callClaude(
      this.apiKey,
      "너는 일반 Q&A 답변기다. 제공된 근거 없이 일반 지식만으로 한국어로 답하라. 이 답변은 명세 검증을 거치지 않은 참고용이다.",
      `질문: ${question}`,
    );
  }

  async classify(question: string): Promise<"A" | "B" | "C"> {
    const raw = await callClaude(
      this.apiKey,
      "질문을 분류하라. A=규칙·수치 질문, B=설계 검증 질문, C=자유 질의.",
      question,
      LAYER_SCHEMA,
    );
    try {
      const layer = JSON.parse(raw).layer;
      if (layer === "A" || layer === "B" || layer === "C") return layer;
    } catch {
      /* fallthrough */
    }
    throw new AppError("LLM_ERROR", "분류 실패", 502, "claude classify: bad output");
  }
}
