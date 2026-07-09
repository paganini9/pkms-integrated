# 03_dev_team 착수 가이드 — Windows PowerShell + Claude Code + GitHub

> 개발 Agent 지시문(v1 확정, `개발_Agent_지시문_초안.md`)에 따라 G0(계약 freeze)부터 착수한다.
> 이 절차는 재현님이 **Windows PowerShell**에서 직접 실행한다(클라우드 세션은 대신 실행 불가).

---

## 0. 사전 준비 (PowerShell에서 설치 확인)

```powershell
node -v        # v20+
python --version  # 3.11+
java -version  # HermiT(추론) 용
docker --version  # Docker Desktop
git --version
gh --version   # (선택) GitHub CLI
claude --version  # Claude Code CLI
```
없는 것은 설치 후 새 PowerShell 창에서 재확인.

## 1. API 키 — Windows 사용자 환경변수 (코드·.env·git 금지)

```powershell
setx ANTHROPIC_API_KEY "sk-..."
setx GOOGLE_AI_API_KEY "AIza..."   # (선택, Gemini)
```
→ **새 PowerShell 창**을 열어야 적용됨. 키는 절대 파일·git에 넣지 않는다.

## 2. 리포 스캐폴딩 (스크립트 실행)

```powershell
cd "C:\Users\jaehyunlee\ClaudeWork\Working\PKMS-Ontology\재기획-2026-07"
powershell -ExecutionPolicy Bypass -File .\setup-dev.ps1
```
→ `Working\pkms-integrated` 생성: `docs\`(요구사항·검토문서), `_coordination\agents\`(dev_team), `knowledge\ontology-ref\`(TTL·satisfy_demo·gen_shacl·project_scope_demo), `frontend\`·`bff\` 골격, git init(main·develop) + 최초 커밋.

## 3. GitHub 연결 (private)

**방법 A — GitHub CLI**
```powershell
cd "C:\Users\jaehyunlee\ClaudeWork\Working\pkms-integrated"
gh repo create pkms-integrated --private --source=. --remote=origin --push
git push -u origin develop
```
**방법 B — 수동**: GitHub에서 빈 private 리포 `pkms-integrated` 생성 후
```powershell
cd "C:\Users\jaehyunlee\ClaudeWork\Working\pkms-integrated"
git remote add origin https://github.com/<계정>/pkms-integrated.git
git push -u origin main
git push -u origin develop
```

## 4. Claude Code 착수 (G0)

```powershell
cd "C:\Users\jaehyunlee\ClaudeWork\Working\pkms-integrated"
claude
```
`claude`가 뜨면 아래 **킥오프 프롬프트**를 붙여넣는다:

```
너는 이 리포의 개발 오케스트레이터다(_coordination/agents/00_오케스트레이터_지시문.md 및 docs/개발_Agent_지시문_초안.md의 팀 매핑·작업순서·제약·DoD를 따른다).

입력 문서: docs/개발_요구사항_명세서.md · docs/기술_설계_명세서.md · docs/수용기준_및_테스트_시나리오.md · docs/개발_Agent_지시문_초안.md, 그리고 _coordination/agents/01~09. 참조 구현: knowledge/ontology-ref/(satisfy_demo.py·gen_shacl.py·project_scope_demo.py·TTL).

지금은 Phase 0 (계약 freeze, 게이트 G0)만 수행한다:
1. 리포 골격 확정 — frontend/(React+TS+Vite), bff/(Node/Express: 인증·AI Gateway·SSE·지식서비스 클라이언트), knowledge/(Python FastAPI: Oxigraph·owlready2/HermiT·pySHACL·satisfy 엔진·규칙 컴파일러·Chroma RAG).
2. _coordination/contracts/ 에 우리 아키텍처 계약을 freeze: api_standard(/api/v1) · BFF↔지식서비스 인터페이스 계약 · 에러 모델 · state/스키마 · mock fixtures. 근거는 기술_설계_명세서.md §6 API 명세.
3. 각 의미있는 단계마다 한글 커밋 + `git push origin develop`. G0 완료 시 태그 `g0-contracts`.
4. 제약(반드시): 레이어 분리(지식·추론·RAG는 knowledge만), 내부 구조 비노출(BFF만 외부·/api/v1), 키는 시스템 환경변수(코드·.env·git 금지·로그 마스킹), MOCK 우선(키 없이 전 흐름), 결정론 우선(satisfy·검증은 reasoner/SHACL), 테스트 우선, 모든 산출 한글.
5. G0 게이트(계약 freeze) 통과 여부를 보고하고, Phase 1(02 데이터·03 RAG·04 그래프코어·06 퍼시스턴스) 병렬 착수 승인을 요청한다.
```

## 5. git 워크플로 (개발 중 상시)

- `main`(안정)·`develop`(개발). 에이전트/단계별 feature 브랜치 → develop 머지.
- 각 게이트·단계 완료마다 **커밋 + 푸시**. 게이트 태그: `g0-contracts` → `g1-*` → `g2-e2e`.
- 키·시크릿은 절대 커밋 금지(`.gitignore`에 `.env` 계열 포함됨). PR은 필요 시 재현님이 요청.

## 6. 참고
- 이 클라우드 세션은 GitHub 생성·푸시·Claude Code 실행을 대신할 수 없어, 위 명령을 재현님 PowerShell에서 실행한다.
- WSL2에서 진행하려면 경로만 `~/pkms-integrated`로 바꾸고 키는 `~/.bashrc`(export)로 두면 된다.
