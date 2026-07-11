# 템플릿 잔재 정정 지시 — `00_오케스트레이터_지시문.md` · `작업분해_의존성맵.md`

> 문제: `_coordination/agents/`의 두 문서가 **MacroLens 스쿼드 템플릿 잔재**를 그대로 갖고 있다(`macrolens/`, `/chat`·`/pins`, Streamlit, SQLite, "섹터·코인", `SC-A/B/C`). `task_board.md`는 PKMS로 이미 적응됐으나, 이 두 문서의 §5 체크리스트·§4 시드가 PKMS의 실제 표면과 어긋나 QA(08)·DevOps(09)가 오독할 수 있다.
> 조치: 아래 변경 맵대로 **문서만** 수정(코드·계약 무관, 동작 불변). 브랜치 `docs/pkms-orchestrator-cleanup`, 한글 커밋.
> 기준(권위): 외부 표면 = BFF `/api/v1/{extraction/stream·validate·save, satisfy, qa, graph, health, upper-ontology/*, rules/*}`. 지식서비스는 내부. 프론트=React(Vite+TS+Tailwind+Cytoscape). 시나리오=SC-1~4·SC-6~8. 저장=Oxigraph(트리플)+Chroma(벡터), SQLite 없음.

---

## A. `00_오케스트레이터_지시문.md`

| 위치 | 현재(잔재) | 정정 |
|------|-----------|------|
| §0 역할 | "**MacroLens 개발 스쿼드**의 테크리드/매니저" | "**PKMS 통합(와이퍼 지식·온톨로지) 개발 스쿼드**의 테크리드/매니저" |
| §1 | "코드 = 레포(`macrolens/`)." | "코드 = 레포(`pkms-integrated/`: `frontend`·`bff`·`knowledge`)." |
| §1 | "조정 = `deliverables/개발/_coordination/`:" | "조정 = `_coordination/`:" |
| §1 | "명세 근거 = `deliverables/개발준비/`(SRS·기술설계·수용기준), `docs/`." | "명세 근거 = `docs/`(SRS·기술설계·수용기준·Solar-AI백엔드-통합가이드·임베딩-로컬-전환-지침)." |
| §개발 환경 | "Python 작업은 `macrolens/backend/.venv`(Python 3.12) … 호스트 3.14 직접 사용 금지." | "Python 작업은 `knowledge/.venv`(Python 3.12) 또는 Docker(python:3.12-slim). 호스트 파이썬 직접 사용 금지." |

**§5 통합 게이트 체크리스트 — 아래 블록으로 교체**(잔재 3줄: 추적성 SC-A/B/C · 경계 `/chat·/pins` · 재현성 분기노드):

```markdown
## 5. 통합 게이트 체크리스트
- [ ] 추적성: P0 시나리오(SC-1~4 · SC-6~8) → FR(FR-01~16) → 구현 → 테스트 연결.
- [ ] 계약 준수: 각 레이어 입출력이 `contracts/`와 일치(스키마 검증 통과).
- [ ] 경계: 지식·추론·RAG 내부 구조가 BFF 외부로 과노출되지 않음(외부는 BFF `/api/v1/{extraction·satisfy·qa·graph·health, 관리자 게이트}`만; 지식서비스는 내부).
- [ ] 안전: 진입 가드레일 + 출력 면책·불확실성·"근거 부족" 분기 동작.
- [ ] 신뢰성: Timeout/Retry/Breaker/Idempotency 중 ≥2 구현.
- [ ] 재현성: 추출 temp 낮음·structured, 결정론 검증(satisfy·SHACL·reasoner)은 같은 입력→같은 판정.
- [ ] QA: 회귀셋·수용기준(AC-1~8) 통과, 환각 0·출처 부착 100%.
- [ ] 패키징: 로컬·Docker 양쪽 실행 동일.
```

## B. `작업분해_의존성맵.md`

| 위치 | 현재(잔재) | 정정 |
|------|-----------|------|
| §1 DAG 리프 | "04 그래프·코어 (**graph/+llm/**)" | "04 추론·코어 (**reasoning/**: satisfy·규칙컴파일러·reasoner·SHACL)" |
| §1 DAG 리프 | "06 퍼시스턴스(DB·FS) (store/ + 스키마)" | "06 퍼시스턴스 (**store/**: Oxigraph 영속·`/sparql`·`kg/save`)" |
| §1 DAG Phase 2 | "05 백엔드·API (04+06 결합, **/chat SSE**)" | "05 백엔드·API (BFF: **/extraction SSE·/satisfy·/qa·/graph**, 04+06 결합)" |
| §2 게이트 | "G2 E2E: **SC-A 한 줄 결론→섹터·코인→출처**가 프론트에서 끝까지 스트리밍." | "G2 E2E: **SC-1 지식입력→SC-2 satisfy→SC-3 Q&A/환각비교**가 실제 BFF로 프론트에서 끝까지 동작(추출 SSE·출처 부착)." |
| §3 병렬 묶음 | "03 RAG \| 계약 + **`rag_corpus/`(존재)**" | "03 RAG \| 계약 + **시드 TTL(6문장)**" |
| §5 임계 경로 | "01 계약(G0) → **04 그래프 코어** → 05 API(G2) → 08 QA 게이트 → 09 패키징" | "01 계약(G0) → **04 satisfy·추론 코어** → 05 BFF API(G2) → 08 QA 게이트 → 09 패키징" |

**§4 대표 작업 시드 — 전면 MacroLens(데이터클라이언트·SQLite·State노드·/chat·Streamlit). 아래 PKMS 실태스크 요약으로 교체**(상세·최신 권위는 `task_board.md`):

```markdown
## 4. 대표 작업(task) — PKMS 실제 매핑 (상세·최신은 task_board.md 권위)
- T-01 레포 골격 frontend/bff/knowledge + core (01) · T-02 contracts freeze → **G0** (01)
- T-10 시드 TTL 적재·정규화 (02) · T-11 6문장·규칙·카테고리 일관성 (02)
- T-20 임베딩(로컬 ST/MOCK)+Chroma (03) · T-21 하이브리드 검색+충분성 (03) · T-22 카테고리·프로젝트 지식선택 (03)
- T-30 satisfy 엔진(3단계) (04) · T-31 규칙 컴파일러(문장→규칙→SHACL) (04) · T-32 /validate/shacl (04) · T-33 reasoner HermiT+owlrl폴백 (04) · T-34 satisfy 시그니처 캐시 (04)
- T-40 Oxigraph 영속+/sparql(읽기) (06) · T-41 kg/save·delete 트리플+벡터 원자성 (06) · T-42 프로젝트·요구·지식범위 CRUD (06)
- T-55 내부 엔드포인트 /kg/lookup·/graph·/dashboard·/governance/*·/upper-ontology/*·GET /rules (04·06) → **G1**
- T-50 AI Gateway(Solar/Mock/Claude/Gemini)+Timeout·Retry·Breaker (05) · T-51 /extraction stream+validate+save(HITL) (05) · T-52 /satisfy 무변형 (05) · T-53 /qa A/B/C+환각비교 (05) · T-54 /graph·/dashboard·admin(403 게이트) (05)
- T-60 핵심 3화면(지식입력·설계검증·Q&A/환각비교) (07) · T-61 지식맵 Cytoscape(inferred 점선) (07) · T-62 에러UX·amber 승인차단 (07) → **G2**
- T-70~73 QA(회귀셋·수용기준·LLM-judge·unknown_concept) (08·04) · T-80~82 DevOps(Docker·시드적재·CI) (09) → **릴리스**
```

---

## C. 오케스트레이터 붙여넣기 프롬프트

```
_coordination/agents/00_오케스트레이터_지시문.md 와 작업분해_의존성맵.md 에 남은 MacroLens 템플릿 잔재를 PKMS 로 정정한다. 문서만 수정하고 코드·계약은 건드리지 않는다(동작 불변). 브랜치 docs/pkms-orchestrator-cleanup, 한글 커밋:

1. docs/템플릿잔재-PKMS정정-지시.md 의 A·B 표대로 라인 단위 치환을 적용한다(macrolens/→pkms-integrated, /chat·/pins→/api/v1 실표면, 섹터·코인→와이퍼 SC-1~3, SC-A/B/C→SC-1~8, macrolens/backend/.venv→knowledge/.venv 등).
2. 00 의 §5 체크리스트, 작업분해의 §4 시드를 지시서의 교체 블록으로 통째로 갈아끼운다.
3. 정정 후, 두 문서에 macrolens·/chat·/pins·Streamlit·SQLite·섹터·코인·SC-A 문자열이 0건인지 grep 으로 확인해 보고한다.
4. task_board.md 는 이미 PKMS 라 수정 불필요 — 두 문서를 task_board 와 정합만 맞춘다.

완료 후 develop 머지. 무엇을 바꿨는지 한글 요약.
```
