/**
 * MockProvider — 키 없이 전 흐름을 끝까지 돌리는 결정론 provider (불변원칙 5).
 * 키워드 사전 기반. 판정은 하지 않는다 — 개념/관계 초안·분류·문장 생성만.
 */
import {
  EmptyContextError,
  type AIProvider, type Concept, type ExtractionEvent, type Predicate, type RequirementDraft, type Source,
} from "./types.js";

interface Lex {
  label: string;
  type: Concept["type"];
  iri: string;
  aliases: string[];
}

const LEXICON: Lex[] = [
  { label: "겨울철", type: "EnvCondition", iri: "http://ex.org/domain#Winter", aliases: ["겨울", "저온"] },
  { label: "고무", type: "Material", iri: "http://ex.org/domain#Rubber", aliases: ["러버"] },
  { label: "실리콘", type: "Material", iri: "http://ex.org/domain#Silicone", aliases: [] },
  { label: "소음", type: "Symptom", iri: "http://ex.org/domain#Noise", aliases: [] },
  { label: "끝단 떨림", type: "Symptom", iri: "http://ex.org/domain#TipChatter", aliases: ["떨림", "채터"] },
  { label: "경도", type: "Attribute", iri: "http://ex.org/domain#Hardness", aliases: [] },
  { label: "와이퍼 암", type: "Component", iri: "http://ex.org/domain#WiperArm", aliases: ["암", "스프링"] },
  { label: "중형 SUV", type: "VehicleType", iri: "http://ex.org/domain#MidSizeSUV", aliases: ["suv"] },
  { label: "소형 세단", type: "VehicleType", iri: "http://ex.org/domain#CompactSedan", aliases: ["세단"] },
];

function findConcepts(text: string): Concept[] {
  const lower = text.toLowerCase();
  const out: Concept[] = [];
  for (const lex of LEXICON) {
    const needles = [lex.label, ...lex.aliases];
    for (const n of needles) {
      const idx = lower.indexOf(n.toLowerCase());
      if (idx >= 0) {
        out.push({ label: lex.label, type: lex.type, iri: lex.iri, span: [idx, idx + n.length] });
        break;
      }
    }
  }
  return out;
}

/** 개념 집합에서 인과 관계 초안을 만든다 (문장 파싱의 결정론 대체). */
function findRelations(text: string, concepts: Concept[]): Array<{ r: import("./types.js").Relation }> {
  const by = (t: Concept["type"]) => concepts.find((c) => c.type === t);
  const out: Array<{ r: import("./types.js").Relation }> = [];
  const material = by("Material");
  const symptom = by("Symptom");
  const env = by("EnvCondition");
  const attr = by("Attribute");
  if (material && symptom) {
    const pred: Predicate = material.label === "실리콘" ? "mitigates" : "causes";
    out.push({ r: { subject: material.label, predicate: pred, object: symptom.label, evidence: text, confidence: 0.9 } });
  }
  if (symptom && env) {
    out.push({ r: { subject: symptom.label, predicate: "conditionedOn", object: env.label, evidence: text, confidence: 0.85 } });
  }
  // 범위 위반 재현: '경도'가 EnvCondition(겨울철)을 causes 하는 초안 (검증 단계에서 잡힌다).
  if (attr && env && !symptom) {
    out.push({ r: { subject: attr.label, predicate: "causes", object: env.label, evidence: text, confidence: 0.6 } });
  }
  return out;
}

export class MockProvider implements AIProvider {
  readonly name = "mock" as const;

  async *extract(text: string): AsyncIterable<ExtractionEvent> {
    yield { kind: "status", stage: "extract", msg: "개념 추출 중" };
    const concepts = findConcepts(text);
    for (const c of concepts) yield { kind: "concept", concept: c };
    for (const { r } of findRelations(text, concepts)) yield { kind: "relation", relation: r };
  }

  async parseRequirements(text: string): Promise<RequirementDraft[]> {
    const out: RequirementDraft[] = [];
    if (/소음|저소음/.test(text)) out.push({ forbids_symptom: "Noise", label: "겨울 저소음(소음 없음)" });
    if (/떨림|채터|chatter/i.test(text)) out.push({ forbids_symptom: "TipChatter", label: "끝단 떨림 없음" });
    // 미지 증상(예: 유막)은 초안에 실어 보내고 지식서비스가 존재 검증한다.
    if (/유막|얼룩/.test(text)) out.push({ forbids_symptom: "유막", label: "유막 없음" });
    return out;
  }

  async answer(question: string, context: Source[]): Promise<string> {
    if (context.length === 0) throw new EmptyContextError(); // CD-14: 검증 답변은 근거 없이 만들지 않는다.
    const cites = context
      .map((s) => s.sentence ?? s.rule)
      .filter(Boolean)
      .join(", ");
    return `근거(${cites})에 따르면 다음과 같습니다. ${context.map((s) => s.text).filter(Boolean).join(" ")}`.trim();
  }

  async llmOnlyAnswer(question: string): Promise<string> {
    // CD-14: 환각비교 전용. 검증되지 않은 단독 답변.
    return `[무근거 LLM 단독] "${question}" 에 대해 일반 지식만으로 답변했습니다. 명세 검증을 거치지 않았습니다.`;
  }

  async classify(question: string): Promise<"A" | "B" | "C"> {
    return classifyByKeyword(question);
  }
}

/** 키워드 규칙 폴백 (interface_contracts.md §4). LLM 분류 실패·mock 시 사용. */
export function classifyByKeyword(question: string): "A" | "B" | "C" {
  const q = question.toLowerCase();
  // B: 설계 검증 질문 — 먼저 본다("~써도 될까"에 스프링 등 설계어가 섞여도 A 로 새지 않게).
  if (
    /(될까|되나|가능|괜찮)/.test(question) &&
    (/mm/.test(q) || /고무|실리콘|설계|블레이드|재질|차종/.test(question))
  ) {
    return "B";
  }
  // A: 규칙·수치 질문
  if (
    (/안전/.test(question) && /길이/.test(question)) ||
    /스프링|규칙|근거 문장|몇\s*n\b/.test(question)
  ) {
    return "A";
  }
  return "C";
}
