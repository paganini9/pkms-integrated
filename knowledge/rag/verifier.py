"""규칙 검증기 — 문장이 파생한 규칙이 SPARQL/SHACL 검증을 통과했는가.

계약(interface_contracts.md §1.1): **`verified=False` 인 hit 는 답변 근거로 쓰이면 안 된다**
(루브릭: 미검증 근거 0). 이 판정은 검색 결과에 실어 보내되, 충분성(`sufficient`)은
`verified=True` hit 가 1건 이상일 때만 True.

04 그래프코어의 규칙 컴파일러가 아직 없으므로 두 구현을 제공한다:
- `CompiledRuleVerifier` — 주입된 컴파일러의 게이트 집합에 규칙이 있으면 True.
- `MockRuleVerifier`(기본) — 규칙이 `rules.ttl` 에 존재하고, 프로젝트 카테고리 필터(있다면)에
  포함되면 True.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RuleVerifier(Protocol):
    def is_verified(self, rule_id: str | None, categories: set[str] | None) -> bool: ...


class MockRuleVerifier:
    """규칙 존재 + 카테고리 필터 기반 판정(컴파일러 미가용 시 기본값).

    `known_rules`: rule_id → category. `rules.ttl` 에서 추출해 주입한다.
    """

    def __init__(self, known_rules: dict[str, str] | None = None) -> None:
        self.known_rules = known_rules or {}

    def is_verified(self, rule_id: str | None, categories: set[str] | None) -> bool:
        if not rule_id or rule_id not in self.known_rules:
            return False
        if categories is None:
            return True
        # CD-4: 프로젝트가 선택한 카테고리 밖 규칙은 미검증 취급(범위 밖 근거 배제)
        return self.known_rules[rule_id] in categories


class CompiledRuleVerifier:
    """04 규칙 컴파일러가 산출한 **컴파일된 규칙 집합**으로 판정 (CD-9).

    `verified` = 이 문장의 규칙이 프로젝트 지식범위로 컴파일되었는가.
    **게이트(`gate_rules`)가 아니라 컴파일된 규칙 전체(`rule_ids`)를 쓴다** — `mitigate` 규칙은
    SHACL 게이트를 만들지 않지만(원인의 여집합) 엄연히 검증된 지식이다. AC-2 는 설계 B 가
    만족하는 근거로 S2(실리콘→소음 해소)·S5(세단 550mm 무해)를 요구하는데, 둘 다 mitigate 다.
    게이트 기준으로 판정하면 이 근거들이 답변에서 사라진다.

    미검증이 되는 경우: 규칙을 모르거나(unknown), **프로젝트 지식범위 밖**이거나(CD-4), 컴파일 실패.
    """

    def __init__(
        self,
        rule_ids: set[str] | None = None,
        compiler=None,  # noqa: ANN001 — 04 RuleCompiler(선택). None 이면 rule_ids 고정 사용
    ) -> None:
        self.rule_ids = rule_ids or set()
        self.compiler = compiler

    def is_verified(self, rule_id: str | None, categories: set[str] | None) -> bool:
        if not rule_id:
            return False
        known = self.rule_ids
        if self.compiler is not None:
            try:
                compiled = self.compiler.compile(categories)
                known = getattr(compiled, "rule_ids", known) or known
            except Exception:  # noqa: BLE001 — 컴파일 실패 시 주입된 고정 집합으로 폴백
                pass
        return rule_id in known
