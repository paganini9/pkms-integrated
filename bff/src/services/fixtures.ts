/**
 * contracts/mocks 로더 — 계약을 만족하는 정답 fixture 를 읽는다.
 * fixture 는 **읽기 전용**이다(절대 수정 금지). `_` 접두 메타 키(_comment·_request·_variant_*)는 벗긴다.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// bff/src/services  ·  bff/dist/services  → 둘 다 3 단계 위가 리포 루트.
const MOCKS_DIR = resolve(here, "../../../_coordination/contracts/mocks");

/** 최상위 `_` 키를 제거해 계약 응답 형태만 남긴다. */
export function stripMeta<T extends Record<string, unknown>>(obj: T): T {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (k.startsWith("_")) continue;
    out[k] = v;
  }
  return out as T;
}

const cache = new Map<string, Record<string, unknown>>();

/** 원본 fixture(메타 포함) 를 읽는다. */
export function readFixtureRaw(name: string): Record<string, unknown> {
  const key = name;
  const cached = cache.get(key);
  if (cached) return structuredClone(cached);
  const raw = JSON.parse(readFileSync(resolve(MOCKS_DIR, `${name}.json`), "utf8")) as Record<string, unknown>;
  cache.set(key, raw);
  return structuredClone(raw);
}

/** 메타를 벗긴 계약 응답을 읽는다. */
export function loadFixture(name: string): Record<string, unknown> {
  return stripMeta(readFixtureRaw(name));
}
