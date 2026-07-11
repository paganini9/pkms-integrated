/**
 * HTTP LLM provider 공통 로직 (T-88).
 *
 * 추출·요구파싱·답변·분류의 **프롬프트와 스키마와 파싱**을 한 곳에 둔다. provider 별 차이는
 * transport(`complete`) 하나뿐이다. 목적: **도메인-엄격 추출 프롬프트가 provider 간 갈리지 않게** 한다.
 * 가드레일(도메인 밖 개념 미추출)은 운영 provider=Solar 에서도 Claude 와 **동일**해야 한다.
 *
 * 판정(satisfies·conforms·violations)은 절대 LLM 출력으로 채우지 않는다 (불변원칙 3).
 */
import { AppError } from "../../core/errors.js";
import {
  CONCEPT_TYPES, EmptyContextError, PREDICATES,
  type AIProvider, type Concept, type ExtractionEvent, type ProviderName,
  type Relation, type RequirementDraft, type Source,
} from "./types.js";

export interface JsonSchema {
  type: "object";
  properties: Record<string, unknown>;
  required: string[];
  additionalProperties: false;
}

export const EXTRACT_SCHEMA: JsonSchema = {
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

export const LAYER_SCHEMA: JsonSchema = {
  type: "object",
  properties: { layer: { type: "string", enum: ["A", "B", "C"] } },
  required: ["layer"],
  additionalProperties: false,
};

const REQ_SCHEMA: JsonSchema = {
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

// ── 시스템 프롬프트 (provider 공통 — 여기만 고친다) ─────────────────────────────
// 주의(CD-13): 이 프롬프트의 **도메인 엄격성이 현재 가드레일의 1차 방어선**이다. 완화하면
// 도메인 낱말을 섞은 우회 질문(예: "자전거 체인에 실리콘…")이 접지를 통과해 샌다(실측).
// 결정론적 접지(온톨로지 소속)는 T-73 이 넣는다 — 그 전까지 이 문구를 약화하지 말 것.
export const SYS_EXTRACT =
  "너는 **와이퍼 블레이드 도메인** 전용 지식 추출기다. 이 도메인의 개념만 뽑는다: " +
  "블레이드 재질(고무·실리콘 등), 차종(중형 SUV·소형 세단), 와이퍼 부품(암·스프링), " +
  "증상(소음·끝단 떨림), 환경(겨울철 저온), 관련 속성/거동. " +
  "**입력이 다른 도메인(타이어·엔진·자전거·노트북·귀마개·신발·일반 윤활유 등)이면 그 개념을 추출하지 마라.** " +
  "와이퍼 도메인 개념이 하나도 없으면 concepts 와 relations 를 **빈 배열**로 반환한다. " +
  "type·predicate 는 주어진 열거형만. 판정하지 말고 추출만 한다.";
const SYS_PARSE_REQ =
  "너는 요구사항 파서다. 자연어 요구를 '금지 증상' 단위로 분해해라. 존재하지 않는 증상도 추정해 실어라(존재 검증은 뒤 단계가 한다).";
const SYS_ANSWER =
  "너는 와이퍼 설계 Q&A 답변기다. 판정 근거는 이미 결정론 엔진이 정했다. 주어진 근거로만 한국어 답변을 작성한다. 근거에 없는 내용은 덧붙이지 않는다.";
const SYS_LLM_ONLY =
  "너는 일반 Q&A 답변기다. 제공된 근거 없이 일반 지식만으로 한국어로 답하라. 이 답변은 명세 검증을 거치지 않은 참고용이다.";
const SYS_CLASSIFY =
  "와이퍼 블레이드 도메인 질문을 A·B·C 중 하나로 분류하라.\n" +
  "A = 규칙·기준·수치 자체를 묻는 질문. 예: '중형 SUV 안전 길이는?', '스프링 최소 압력은 몇 N?', '최대 안전 길이 알려줘'.\n" +
  "B = 구체적 설계안(재질·길이·스프링·암형상·차종 등 속성이 주어짐)이 요구를 만족하는지 검증·판정하는 질문. " +
  "예: '중형 SUV에 고무 600mm 스프링 8N simple 암 써도 될까?', '실리콘 550mm 세단용 괜찮아?'.\n" +
  "C = A·B 에 속하지 않는 자유 질의. 예: '겨울에 고무 블레이드 쓰면 소음이 나나요?'.\n" +
  "판단 지침: 설계 속성 수치가 구체적으로 주어지고 '써도 될까/괜찮나' 식이면 B. 기준·수치를 되묻는 것이면 A.";

/** 마크다운 코드펜스(```json … ```)를 벗겨 순수 JSON 문자열을 얻는다(프롬프트 폴백 대비). */
export function stripFences(s: string): string {
  const t = s.trim();
  const m = t.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return (m?.[1] ?? t).trim();
}

export abstract class BaseHttpProvider implements AIProvider {
  abstract readonly name: ProviderName;

  /** system+user(+선택 schema) → 텍스트(JSON 문자열일 수 있음). provider 별 transport 만 다르다. */
  protected abstract complete(system: string, user: string, schema?: JsonSchema): Promise<string>;

  protected parseJson<T>(raw: string, label: string): T {
    try {
      return JSON.parse(stripFences(raw)) as T;
    } catch {
      throw new AppError("LLM_ERROR", "AI 응답에 실패했습니다.", 502, `${this.name} ${label}: JSON parse fail`);
    }
  }

  async *extract(text: string): AsyncIterable<ExtractionEvent> {
    const raw = await this.complete(SYS_EXTRACT, text, EXTRACT_SCHEMA);
    const parsed = this.parseJson<{ concepts?: Concept[]; relations?: Relation[] }>(raw, "extract");
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
    const raw = await this.complete(SYS_PARSE_REQ, text, REQ_SCHEMA);
    return this.parseJson<{ requirements?: RequirementDraft[] }>(raw, "parseRequirements").requirements ?? [];
  }

  async answer(question: string, context: Source[]): Promise<string> {
    if (context.length === 0) throw new EmptyContextError(); // CD-14: 검증 답변은 근거 없이 만들지 않는다.
    const ctx =
      "다음 검증된 근거만 사용해 답하라:\n" +
      context.map((s) => `- [${s.sentence ?? s.rule}] ${s.text ?? ""}`).join("\n");
    return this.complete(SYS_ANSWER, `질문: ${question}\n\n${ctx}`);
  }

  async llmOnlyAnswer(question: string): Promise<string> {
    // CD-14: 환각비교 전용. verified_answer 에 절대 쓰지 않는다.
    return this.complete(SYS_LLM_ONLY, `질문: ${question}`);
  }

  async classify(question: string): Promise<"A" | "B" | "C"> {
    const raw = await this.complete(SYS_CLASSIFY, question, LAYER_SCHEMA);
    const layer = this.parseJson<{ layer?: string }>(raw, "classify").layer;
    if (layer === "A" || layer === "B" || layer === "C") return layer;
    throw new AppError("LLM_ERROR", "분류 실패", 502, `${this.name} classify: bad output`);
  }
}
