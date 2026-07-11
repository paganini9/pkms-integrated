"""레이어 Protocol — `_coordination/contracts/interface_contracts.md` §2 의 코드 표현.

각 Agent 는 자기 Protocol 을 구현하고, 남의 레이어는 `mocks.py` 의 mock 으로 대체해 선행 개발한다.
서로를 기다리지 않는 것이 Phase 1 병렬화의 전제다.
"""
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from schemas.models import (
    Design,
    RagHit,
    SatisfyResponse,
    SavedSentence,
    Violation,
)

if TYPE_CHECKING:
    from rdflib import Graph


class ConsistencyResult(Protocol):
    consistent: bool
    clashes: list[str]


class ShaclReport(Protocol):
    conforms: bool
    violations: list[Violation]


class CompiledRules(Protocol):
    """gen_shacl.compile_rules 의 산출 — SHACL 게이트 · 인과엣지 · 사람용 뷰."""

    shapes: "Graph"
    causal_edges: "Graph"
    human_view: list[str]


# ── 06 퍼시스턴스 ──────────────────────────────────────────────────────────
@runtime_checkable
class Store(Protocol):
    def query(self, sparql: str, *, readonly: bool = True) -> list[dict]: ...
    def save_sentence(self, sentence_text: str, category: str, mentions: list[str]) -> SavedSentence: ...
    def delete(self, iri: str) -> None: ...
    def subgraph(self, iris: list[str], depth: int = 2) -> "Graph": ...
    def load_seed(self, ttl_paths: list[str]) -> int: ...


# ── 04 그래프·코어 ─────────────────────────────────────────────────────────
@runtime_checkable
class Reasoner(Protocol):
    def consistency(self, graph: "Graph") -> ConsistencyResult: ...
    def classify(self, iri: str) -> list[str]: ...
    def validate_shacl(self, data: "Graph", shapes: "Graph") -> ShaclReport: ...


@runtime_checkable
class RuleCompiler(Protocol):
    """문장 → 구조화 DesignRule → SHACL·인과엣지·사람뷰. 단일 진실원은 rules.ttl."""

    def compile(self, categories: set[str] | None = None) -> CompiledRules: ...


@runtime_checkable
class SatisfyEngine(Protocol):
    def satisfy(
        self, design: Design, require: list[str], categories: set[str] | None = None
    ) -> SatisfyResponse: ...


# ── 03 RAG ────────────────────────────────────────────────────────────────
@runtime_checkable
class Embedder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class Retriever(Protocol):
    def search(self, query: str, k: int = 6, project_id: str | None = None) -> list[RagHit]: ...
    def is_sufficient(self, hits: list[RagHit]) -> bool: ...
    def upsert(self, items: list[dict]) -> int: ...
    def delete(self, iris: list[str]) -> int: ...
