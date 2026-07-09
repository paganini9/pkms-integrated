"""계약 fixture 를 그대로 반환하는 mock 구현 (interface_contracts.md §5).

Phase 1 에서 의존 레이어가 미완일 때 사용한다. 실구현이 들어오면 교체하되,
**mock 과 실구현은 같은 Protocol·같은 스키마를 만족해야 한다** — 그것이 G1 인터페이스 적합성 게이트다.
"""
import json
from pathlib import Path
from typing import Any

CONTRACTS = Path(__file__).resolve().parents[2] / "_coordination" / "contracts"
MOCKS = CONTRACTS / "mocks"


def load_fixture(name: str) -> dict[str, Any]:
    """fixture 로드 — 문서용 `_` 접두 키는 제거한다 (mocks/README.md 규약)."""
    doc = json.loads((MOCKS / name).read_text(encoding="utf-8"))
    return _strip_meta(doc)


def _strip_meta(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_meta(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_meta(x) for x in obj]
    return obj


class MockSatisfyEngine:
    """설계 특성으로 fixture 를 고른다. 실엔진 교체 전까지 05/07 이 E2E 를 돌릴 수 있게 한다."""

    def satisfy(self, design, require, categories=None):  # noqa: ANN001
        cats = set(categories or {"소음", "떨림"})
        if design.material == "Silicone":
            return load_fixture("satisfy_good.json")
        if cats == {"떨림"}:
            return load_fixture("satisfy_scope_B.json")
        return load_fixture("satisfy_bad.json")


class MockRetriever:
    def search(self, query, k=6, project_id=None):  # noqa: ANN001
        return load_fixture("rag_search_winter_rubber.json")["hits"][:k]

    def is_sufficient(self, hits):  # noqa: ANN001
        return any(h["verified"] if isinstance(h, dict) else h.verified for h in hits)

    def upsert(self, items):  # noqa: ANN001
        return len(items)

    def delete(self, iris):  # noqa: ANN001
        return len(iris)


class MockEmbedder:
    """결정론적 해시 임베딩 — 키·모델 없이 전 흐름 검증(MOCK 우선)."""

    DIM = 64

    def encode(self, texts: list[str]) -> list[list[float]]:
        import hashlib

        out = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            vec = [(h[i % len(h)] / 255.0) * 2 - 1 for i in range(self.DIM)]
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out


class MockStore:
    def query(self, sparql, *, readonly=True):  # noqa: ANN001
        return []

    def save_sentence(self, sentence_text, category, mentions):  # noqa: ANN001
        return load_fixture("extraction_save_S1.json")["sentence"]

    def delete(self, iri):  # noqa: ANN001
        return None

    def subgraph(self, iris, depth=2):  # noqa: ANN001
        from rdflib import Graph

        return Graph()

    def load_seed(self, ttl_paths):  # noqa: ANN001
        return 0
