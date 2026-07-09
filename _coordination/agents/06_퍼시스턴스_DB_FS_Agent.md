# 06 · 퍼시스턴스(DB·파일시스템) Agent

## 역할
브리핑 히스토리·핀의 영속화와 파일시스템 레이아웃을 설계·구현한다.

## 담당 경로
`backend/app/store/`(sqlite·models·migrations), 파일 레이아웃(데이터·캐시·Chroma 볼륨) 설계.

## 입력 / 계약
`interface_contracts.md#Store`, SRS FR-6·FR-14, 기술설계 §2·§8.

## 작업
1. SQLite 스키마: `briefings`(id·thread_id·created_at·payload_json·trigger_type), `pins`(sector·order), 인덱스.
2. `Store` 구현(get/set pins, save/last/list briefing). 마이그레이션(초기 스키마) + 시드.
3. **파일시스템 설계**: 캐시 디렉터리, `rag_corpus/`(읽기), Chroma 영속 볼륨, SQLite 파일 위치 — **로컬=Docker 동일** 경로를 env로 주입.
4. 단위 테스트(임시 DB) + fixture.

## DoD
- `Store` 계약 충족, 재시작 후 핀·히스토리 유지, FS 레이아웃 문서화.

## 인터페이스
- out: `Store`. 소비자: 05 API·04 그래프(change_detector). 의존: 계약(G0)만 → P1 병렬.
