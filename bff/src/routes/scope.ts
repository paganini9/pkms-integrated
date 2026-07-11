/**
 * CD-4 지식범위 해석 — satisfy·qa(B) 가 프로젝트의 `knowledge_categories` 를 컴파일 필터로 넘긴다.
 * 계약 변경 불필요: 내부 `GET /projects/{id}` 로 조회한다.
 */
import { KnowledgeUnavailable, NotFound } from "../core/errors.js";
import type { KnowledgeClient } from "../services/knowledgeClient.js";

/**
 * 적용할 카테고리를 정한다.
 * - explicit(요청에 직접 실린 categories) 우선.
 * - 없으면 project_id 로 프로젝트를 조회해 knowledge_categories 사용.
 * - project 없음/지식 도달 불가 → null(=전체 범위). satisfy 판정 자체를 막지 않는다.
 */
export async function resolveCategories(
  kn: KnowledgeClient,
  projectId: string | undefined,
  explicit: string[] | undefined,
): Promise<string[] | null> {
  if (explicit && explicit.length > 0) return explicit;
  if (!projectId) return null;
  try {
    const proj = await kn.getProject(projectId);
    const cats = proj.knowledge_categories as string[] | undefined;
    return cats && cats.length > 0 ? cats : null;
  } catch (err) {
    if (err instanceof NotFound || err instanceof KnowledgeUnavailable) return null;
    throw err;
  }
}
