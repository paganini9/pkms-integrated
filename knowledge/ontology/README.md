# ontology/ — 시드 TTL (02 데이터 Agent 소유)

`ontology-ref/`(참조 구현, 읽기 전용)에서 복사한 시드. 기동 시 `Store.load_seed()`가 **멱등 적재**한다.

| 파일 | 층 | 내용 |
|---|:--:|---|
| `m0.ttl` | M0 | 확장 SPMM 상위 온톨로지 (4대 범주 disjoint · 9관계) |
| `m1_wiper.ttl` | M1 | 와이퍼 도메인 · 6문장(S1~S6) · 개념 · 거동 위계 |
| `rules.ttl` | M1 | **구조화 DesignRule (단일 진실원)** — SHACL·인과엣지·사람뷰가 여기서 파생 |
| `shapes.ttl` | M1 | 손수 작성한 SHACL 게이트 (참조·비교용) |
| `m2_instances.ttl` | M2 | 데모 프로젝트 데이터 (Proj_WinterSUV · RB · 설계 A/B) |

## 02 Agent 할 일 (Phase 1)

1. **CD-3 정규화** — `m1_wiper.ttl`은 S4+S6을 `AggravationRule` 하나로 묶어 두었고, `rules.ttl`은 `SpringRule`·`ArmRule`로 나눈다.
   **API가 노출하는 규칙 id는 `rules.ttl` 기준**이므로, `m1_wiper.ttl`의 `dom:derivesRule` 참조를 `rules.ttl` 표기에 맞춘다
   (`S4 derivesRule SpringRule`, `S6 derivesRule ArmRule`). `AggravationRule` 삼중항은 제거한다.
2. `shapes_generated.ttl`은 **파생물이므로 커밋하지 않는다**(`gen_shacl`이 런타임에 생성). `.gitignore` 확인.
3. 시드 적재는 멱등이어야 한다 — 같은 TTL을 두 번 적재해도 트리플 수가 늘지 않을 것.

> `ontology-ref/`는 원본 참조 구현이다. **수정하지 않는다.** 이식 대상은 `reasoning/`(04)·`store/`(06).
