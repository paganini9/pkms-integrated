/** zod 검증 헬퍼 — 위반 시 422 VALIDATION_ERROR + 필드 경로(details). */
import type { z } from "zod";
import { ValidationError } from "./errors.js";

export function parseOrThrow<T>(schema: z.ZodType<T>, data: unknown): T {
  const res = schema.safeParse(data);
  if (!res.success) {
    const first = res.error.issues[0];
    const field = first ? first.path.join(".") : undefined;
    throw new ValidationError(
      `zod: ${res.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
      field ? { field } : undefined,
    );
  }
  return res.data;
}
