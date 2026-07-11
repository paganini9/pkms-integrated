"""T-89 — OOV(온톨로지 밖 용어) 매핑 후보 생성.

접지가 unknown 으로 막은 개념에 대해 **매핑 후보**를 제시한다(막기만 하지 않고 트리아지).
- 어휘 후보: 라벨 문자열 유사도(difflib) — 표기 이형("재질은"→"재질", "블레이드는"→"블레이드").
- 임베딩 후보: 로컬/mock 임베더로 개념 prefLabel 최근접(의미 유사).
후보는 **provisional** 이다 — 승인(altLabel 편입, 거버넌스) 전엔 접지에 쓰이지 않는다(fail-closed 불변).
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass

from rdflib import RDFS, URIRef

from reasoning.spec_validate import DOM, EXT, SPMM, SpecValidator


@dataclass
class Candidate:
    concept: str  # 로컬네임
    iri: str
    pref_label: str
    score: float
    via: str  # "lexical" | "embedding"


def _local(iri: str) -> str:
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _concept_index(v: SpecValidator) -> list[tuple[str, str]]:
    """(iri, prefLabel) — 도메인 개념 목록(후보 대상)."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for s, lbl in v._onto.subject_objects(RDFS.label):  # noqa: SLF001 — 같은 패키지
        if not isinstance(s, URIRef):
            continue
        iri = str(s)
        if iri in seen or not (iri.startswith(str(DOM)) or iri.startswith(str(SPMM)) or iri.startswith(str(EXT))):
            continue
        seen.add(iri)
        text = str(lbl)
        pref = text[: text.index("(")].strip() if "(" in text else text
        out.append((iri, pref))
    return out


def candidates(label: str, validator: SpecValidator, embedder=None, k: int = 3) -> list[Candidate]:  # noqa: ANN001
    """OOV 라벨 → 매핑 후보 top-k. embedder 없으면 어휘 후보만."""
    index = _concept_index(validator)
    out: dict[str, Candidate] = {}

    # ── 어휘 후보(문자열 유사도) — 모든 라벨(alt 포함)과 비교 ──
    all_labels = list(validator._label_to_iri.items())  # noqa: SLF001
    for lbl, iri in all_labels:
        ratio = difflib.SequenceMatcher(None, label, lbl).ratio()
        if ratio >= 0.6:
            key = str(iri)
            pref = next((p for i, p in index if i == key), _local(key))
            prev = out.get(key)
            if prev is None or ratio > prev.score:
                out[key] = Candidate(_local(key), key, pref, round(ratio, 3), "lexical")

    # ── 임베딩 후보(의미 최근접) ──
    if embedder is not None and index:
        try:
            qv = embedder.encode([label])[0]
            lvs = embedder.encode([p for _, p in index])
            sims = [(iri, _cos(qv, lv)) for (iri, _p), lv in zip(index, lvs)]
            for iri, sim in sorted(sims, key=lambda x: x[1], reverse=True)[:k]:
                pref = next((p for i, p in index if i == iri), _local(iri))
                if sim >= 0.35 and (iri not in out or sim > out[iri].score):
                    if iri not in out:  # 어휘 후보가 우선(정확도 높음)
                        out[iri] = Candidate(_local(iri), iri, pref, round(sim, 3), "embedding")
        except Exception:  # noqa: BLE001 — 임베더 실패는 어휘 후보로 계속
            pass

    return sorted(out.values(), key=lambda c: c.score, reverse=True)[:k]


def _cos(a, b) -> float:  # noqa: ANN001
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(x * x for x in b) ** 0.5
    return num / (da * db) if da and db else 0.0
