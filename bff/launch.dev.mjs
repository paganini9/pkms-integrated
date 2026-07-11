/**
 * 로컬 개발/스모크 런처 — 운영 provider(Solar) 실 스택을 한 줄로 띄운다.
 * 비-비밀 env 만 코드로 고정한다(기존 env 가 있으면 존중). **비밀 키는 절대 여기 두지 않는다**:
 * `Studio_API_Key`(Solar) 등은 시스템 환경변수(setx)/컨테이너 env 에서만 주입된다.
 *   node/tsx:  npx tsx launch.dev.mjs   (Studio_API_Key 는 프로세스 env 에 있어야 함)
 * 정식 기동은 Docker/compose(T-80·T-81)가 담당한다. 이 파일은 로컬 편의용.
 */
process.env.AI_MOCK_MODE ??= "false";
process.env.AI_PROVIDER ??= "solar";
process.env.KNOWLEDGE_MOCK ??= "false";
process.env.BFF_PORT ??= "4001";
process.env.KNOWLEDGE_URL ??= "http://127.0.0.1:8000";

await import("./src/index.ts");
