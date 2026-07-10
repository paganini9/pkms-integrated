/**
 * API 경계 스위치 — VITE_USE_MOCK 로 mock/real 교체.
 * 기본값 mock (05 백엔드 BFF 와 병렬 개발; BFF 미완이어도 전 화면 동작).
 * 실제 API 연결 시 `VITE_USE_MOCK=false` 로 빌드/실행한다.
 */
import { mockApi } from "./mockApi";
import { realApi } from "./realApi";
import type { PkmsApi } from "./types";

const useMock = (import.meta.env.VITE_USE_MOCK ?? "true") !== "false";

export const api: PkmsApi = useMock ? mockApi : realApi;
export const USING_MOCK = useMock;

export { ApiCallError } from "./types";
export type * from "./types";
