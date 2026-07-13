"""T-92 — 라벨→IRI 새니타이징.

포스트-g3 실 검증에서 완전히 접지된(violations 0) 초안이 **저장에서 500 으로 죽었다**:
`oxigraph.py` 가 미해석 라벨("오존 노출")을 그대로 IRI 에 이어붙였다 → `Invalid IRI code point ' '`.
"""
from __future__ import annotations

import pytest

from core.config import settings
from schemas.models import Concept, Relation, SaveRequest
from store.kg import KgService
from store.naming import slug_localname
from store.oxigraph import OxigraphStore


class _SpyRetriever:
    def __init__(self) -> None:
        self.upserts: list = []

    def upsert(self, items):  # noqa: ANN001, ANN201
        self.upserts.append(items)
        return len(items)

    def delete(self, iris):  # noqa: ANN001, ANN201
        return len(iris)


@pytest.fixture()
def kg_service(tmp_path) -> KgService:  # noqa: ANN001
    store = OxigraphStore(tmp_path / "oxigraph")
    store.load_seed([p for p in settings.seed_ttl if p.exists()])
    return KgService(store, retriever=_SpyRetriever())


def test_슬러그_멱등_무손실() -> None:
    assert slug_localname("오존") == "오존"
    assert slug_localname("오존") == slug_localname("오존")
    assert slug_localname("WiperBlade") == "WiperBlade"


def test_공백_라벨은_해시_접미로_충돌을_막는다() -> None:
    a, b = slug_localname("오존 노출"), slug_localname("오존_노출")
    assert " " not in a
    assert a != b  # 서로 다른 라벨이 같은 IRI 로 뭉치면 안 된다
    assert slug_localname("오존 노출") == a  # 멱등


@pytest.mark.parametrize("label", ["오존 노출", "외부 화학 물질 노출", "블레이드/프레임", 'a"b<c>', "고속 주행"])
def test_공백_특수문자_라벨_저장_201(kg_service, label: str) -> None:
    """저장이 크래시하지 않고, 표면형은 rdfs:label 로 보존된다."""
    saved = kg_service.save(
        SaveRequest(
            sentence_text=f"{label} 에서 문제가 생긴다.",
            concepts=[Concept(label=label, type="EnvCondition"), Concept(label="균열", type="Symptom")],
            relations=[Relation(subject=label, predicate="causes", object="균열")],
            category="소음",
            approved=True,
            draft_id=f"t92-{slug_localname(label)}",
        )
    )
    assert saved.sentence.iri.startswith("http://ex.org/domain#S")
    ln = slug_localname(label)
    assert ln in saved.sentence.mentions
    rows = kg_service.store.query(
        f'SELECT ?l WHERE {{ <http://ex.org/domain#{ln}> <http://www.w3.org/2000/01/rdf-schema#label> ?l }}',
        readonly=False,
    )
    assert [r["l"] for r in rows] == [label]  # 표면형 보존


def test_시드_개념은_시드_IRI_를_유지한다(kg_service) -> None:
    """어휘층에서 해석되는 라벨은 슬러그가 아니라 시드 로컬네임(WiperBlade)을 쓴다."""
    saved = kg_service.save(
        SaveRequest(
            sentence_text="블레이드는 겨울에 소음이 난다.",
            concepts=[Concept(label="블레이드", type="PartType"), Concept(label="소음", type="Symptom")],
            relations=[Relation(subject="블레이드", predicate="causes", object="소음")],
            category="소음",
            approved=True,
            draft_id="t92-seed-iri",
        )
    )
    assert "WiperBlade" in saved.sentence.mentions
    assert saved.sentence.about_symptom == "Noise"
