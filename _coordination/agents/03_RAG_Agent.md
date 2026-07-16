# 03 · RAG·지식 Agent

## 역할
시드 문장을 검색 가능한 벡터 지식으로 만들고 **하이브리드 검색 + 충분성 판단**을 제공한다.

## 담당 경로
`knowledge/rag/` (`embedder.py`·`retriever.py`·`verifier.py`·`sources.py`·`routes.py`).

## 입력 / 계약
`contracts/interface_contracts.md#(Embedder,Retriever)` §1.1 `POST /rag/search`·`/rag/upsert`. `contracts/README.md` CD-9·CD-12. `docs/임베딩-로컬-전환-지침.md`.

## 작업
1. 임베딩(provider 추상화, 다국어): `EMBEDDING_PROVIDER=local`(sentence-transformers) / `mock`(해시 기반 **결정론** 벡터). **ST 미설치여도 예외 없이 mock 폴백**.
2. Chroma 임베디드 upsert/delete. **컬렉션-임베더 일치 가드**: 컬렉션 메타에 `embedder_model`·`embed_dim` 을 저장하고 불일치 시 drop→recreate(자가치유).
3. 하이브리드 검색 `search(query, k, project_id)` → `Hit{iri, sentence, text, score, about_symptom, derives_rule, verified}`.
4. **`verified` (CD-9)** = 그 문장의 규칙이 **프로젝트 지식범위로 컴파일된 규칙 집합에 속하는가**. `mitigate` 규칙 포함(게이트 여부와 무관 — AC-2 의 근거 S2·S5 가 mitigate 다). 미검증 = 알 수 없는 규칙 · 지식범위 밖(CD-4) · 컴파일 실패.
5. **`verified:false` hit 는 답변 근거로 쓰지 않는다**(루브릭 "미검증 근거 0"). `sufficient` = `verified` hit ≥ 1.
6. **점수 임계값 금지** — mock 임베딩의 절대 점수는 의미가 없다. 도메인 접지(CD-12)는 개념 사전 조회이지 유사도 컷이 아니다.

## DoD
- `Retriever` 계약 충족, 미검증 근거 0, `EMBEDDING_PROVIDER` 양쪽(local·mock) 동작, 컬렉션 가드 테스트 통과.

## 인터페이스
- out: `Retriever`·`Embedder`. 소비자: 05 BFF(Q&A C계층). 의존: 계약(G0) + 시드 TTL(02) → P1 병렬.

## `verified` 는 권위 축이지 관련성 축이 아니다 ★
CD-12 에서 값을 치르고 배웠다. `sufficient = verified hit ≥ 1` 인데 시드 문장은 전부 지식범위 안이라 `verified:true` 이고, 검색은 질문과 무관하게 언제나 상위 `k` 건을 돌려준다 → **`sufficient` 가 항상 참이라 "명세 근거 없음" 분기가 영영 발화하지 않았다**(도메인 밖 질문에 시드 6문장이 전부 근거로 붙었다).
확정: `insufficient_evidence` = **도메인 접지 실패 OR `verified` hit == 0**. 접지 판정은 05 BFF 가 `/qa` 진입 직후 수행한다(CD-13 — 가드레일은 라우팅보다 **앞**). `verified` 의 의미는 바뀌지 않는다 — 관련성 축을 하나 더 얹는 것이다.

## 개발 환경
Python 작업은 `knowledge/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 파이썬 직접 사용 금지. 상세: `공유표준/개발환경.md`.
