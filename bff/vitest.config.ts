import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // 키 없이 mock 우선으로 전 흐름을 돌린다 (DoD 4). 지식서비스도 fixture mock.
    env: {
      AI_MOCK_MODE: "true",
      KNOWLEDGE_MOCK: "true",
      NODE_ENV: "test",
    },
    include: ["test/**/*.test.ts"],
    hookTimeout: 20000,
    testTimeout: 20000,
    // Windows + undici keep-alive 소켓과 tinypool 워커 조기종료 회피(테스트 인프라 안정화).
    pool: "forks",
    poolOptions: { forks: { singleFork: true } },
    fileParallelism: false,
  },
});
