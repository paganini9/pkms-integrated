# 03 · RAG·지식 Agent

## 역할
`rag_corpus/`를 검색 가능한 지식 베이스로 만들고 가중·시차 검색·충분성 판단을 제공한다.

## 담당 경로
`backend/app/rag/` (load·chunk·embed·chroma·retrieve·sufficiency).

## 입력 / 계약
`interface_contracts.md#Retriever`, `Evidence`. `docs/RAG_구축_가이드.md`, `rag_corpus/`(news·knowledge·cases·_manifest.csv).

## 작업
1. 청킹: causal=1문서1청크, case=섹션, news=섹션(인과관찰 별도). YAML front-matter→메타데이터.
2. 임베딩(provider 추상화, 다국어) → Chroma 3컬렉션(kb_causal·kb_cases·kb_news). `_manifest.csv` 기준 증분 upsert.
3. 검색: 필터(sectors·indicators·market) + 가중 결합(`w_causal`/`w_historical`) + 시차(lead_lag·lag_window) 전달.
4. **충분성 판단**(`is_sufficient`) — 부족 시 호출자에 신호(FR-12).
5. 검색 품질 평가셋(precision@k) 초안.

## DoD
- `Retriever` 계약 충족, 3컬렉션 인덱싱·가중/시차 검색·충분성 동작.

## 인터페이스
- out: `Retriever`. 소비자: 04 그래프. 의존: 계약(G0) + rag_corpus(존재) → P1 병렬.

## 적재(인덱싱) — 파일 → ChromaDB  ★
- **인덱싱 스크립트** `python -m app.rag.index` (=`index_incremental()`): `_manifest.csv`+내용 해시로 신규/수정 판별 → 문서 id upsert. ledger(id·해시·임베딩 모델 버전) 보관(모델 교체 시 전체 재인덱싱).
- **트리거(MVP=앱 측 lazy+startup)**: ① 앱 `lifespan` 기동 시 1회(05 백엔드와 협의) + ② `query()` 직전 `ensure_synced()` 증분 동기화 → 쿼리 시점 최신.
- **수집 스케줄은 파일만 쓰고 임베딩하지 않는다**(앱·Chroma와 별 프로세스). 인덱싱 책임은 RAG 레이어.

## 개발 환경
Python 작업은 `macrolens/backend/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 3.14 직접 사용 금지. 상세: `공유표준/개발환경.md`.
