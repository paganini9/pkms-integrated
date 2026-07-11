/**
 * GeminiProvider — Google Generative Language API (generateContent).
 * JSON 응답 모드로 결정론 확보. 키는 env 에서만. 실패 시 gateway 가 mock 폴백한다.
 */
import { config } from "../../core/config.js";
import { AppError } from "../../core/errors.js";
import {
  CONCEPT_TYPES, EmptyContextError, PREDICATES,
  type AIProvider, type Concept, type ExtractionEvent, type Relation,
  type RequirementDraft, type Source,
} from "./types.js";

async function callGemini(apiKey: string, prompt: string, jsonMode: boolean): Promise<string> {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${config.geminiModel}:generateContent?key=${apiKey}`;
  const body: Record<string, unknown> = {
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    generationConfig: { temperature: 0.1, ...(jsonMode ? { responseMimeType: "application/json" } : {}) },
  };
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new AppError("LLM_ERROR", "AI 응답에 실패했습니다.", res.status, `gemini ${res.status}`);
  }
  const data = (await res.json()) as {
    candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
  };
  return (data.candidates?.[0]?.content?.parts ?? []).map((p) => p.text ?? "").join("");
}

export class GeminiProvider implements AIProvider {
  readonly name = "gemini" as const;
  constructor(private readonly apiKey: string) {}

  async *extract(text: string): AsyncIterable<ExtractionEvent> {
    const raw = await callGemini(
      this.apiKey,
      `와이퍼 도메인 문장에서 개념/관계를 JSON 으로 추출하라.\n` +
        `type 열거형: ${[...CONCEPT_TYPES].join("|")}\npredicate 열거형: ${[...PREDICATES].join("|")}\n` +
        `형식: {"concepts":[{"label","type"}],"relations":[{"subject","predicate","object","evidence"}]}\n문장: ${text}`,
      true,
    );
    let parsed: { concepts?: Concept[]; relations?: Relation[] };
    try {
      parsed = JSON.parse(raw);
    } catch {
      throw new AppError("LLM_ERROR", "AI 응답에 실패했습니다.", 502, "gemini extract parse fail");
    }
    yield { kind: "status", stage: "extract", msg: "개념 추출 중" };
    for (const c of parsed.concepts ?? []) if (CONCEPT_TYPES.has(c.type)) yield { kind: "concept", concept: { label: c.label, type: c.type } };
    for (const r of parsed.relations ?? []) if (PREDICATES.has(r.predicate)) yield { kind: "relation", relation: r };
  }

  async parseRequirements(text: string): Promise<RequirementDraft[]> {
    const raw = await callGemini(
      this.apiKey,
      `요구사항을 금지증상 단위로 분해해 JSON {"requirements":[{"forbids_symptom","label"}]} 로 반환하라.\n요구: ${text}`,
      true,
    );
    try {
      return (JSON.parse(raw).requirements ?? []) as RequirementDraft[];
    } catch {
      throw new AppError("LLM_ERROR", "AI 응답에 실패했습니다.", 502, "gemini parseRequirements parse fail");
    }
  }

  async answer(question: string, context: Source[]): Promise<string> {
    if (context.length === 0) throw new EmptyContextError(); // CD-14
    const ctx = "다음 검증된 근거만 사용:\n" + context.map((s) => `- [${s.sentence ?? s.rule}] ${s.text ?? ""}`).join("\n");
    return callGemini(this.apiKey, `질문: ${question}\n${ctx}\n근거에 없는 내용은 덧붙이지 말고 한국어로 답하라.`, false);
  }

  async llmOnlyAnswer(question: string): Promise<string> {
    // CD-14: 환각비교 전용.
    return callGemini(this.apiKey, `질문: ${question}\n근거 없이 일반 지식으로 한국어로 답하라(참고용, 미검증).`, false);
  }

  async classify(question: string): Promise<"A" | "B" | "C"> {
    const raw = await callGemini(
      this.apiKey,
      `질문 분류. A=규칙/수치, B=설계검증, C=자유질의. JSON {"layer":"A|B|C"} 로만.\n질문: ${question}`,
      true,
    );
    try {
      const layer = JSON.parse(raw).layer;
      if (layer === "A" || layer === "B" || layer === "C") return layer;
    } catch {
      /* fallthrough */
    }
    throw new AppError("LLM_ERROR", "분류 실패", 502, "gemini classify bad output");
  }
}
