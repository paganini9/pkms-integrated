"""RAG 라우터 — 지식서비스 내부 API(prefix 없음).

- POST /rag/search  → RagSearchResponse
- POST /rag/upsert  → {"upserted": n, "trace_id"}
- POST /rag/delete  → {"deleted": n, "trace_id"}
- GET  /categories  → {"categories":[{"name","sentences","rules"}], "trace_id"}

실패는 `schemas.errors.RagError` 를 던진다(응답 본문은 main.py 의 핸들러가 만든다).
`get_retriever()` 는 의존성 함수로 싱글턴을 제공 — 모듈 최상단에서 Chroma 를 열지 않는다.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from core.logging import get_trace_id
from schemas.errors import RagError
from schemas.models import RagSearchRequest, RagSearchResponse

from .retriever import ChromaRetriever

log = logging.getLogger("rag.routes")
router = APIRouter()

_retriever: ChromaRetriever | None = None


def get_retriever() -> ChromaRetriever:
    """싱글턴 검색기. 최초 호출 시 Chroma 를 열고 초기 인덱싱을 수행한다."""
    global _retriever
    if _retriever is None:
        try:
            r = ChromaRetriever()
            r.ensure_indexed()
            _retriever = r
        except Exception as exc:  # noqa: BLE001
            raise RagError(internal=f"검색기 초기화 실패: {exc!r}") from exc
    return _retriever


# ── upsert/delete 요청 모델(rag 레이어 내부 정의) ────────────────────────────
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RagUpsertItem(_Strict):
    iri: str = Field(min_length=1)
    text: str = ""
    sentence: str | None = None
    category: str | None = None
    about_symptom: str | None = None
    derives_rule: str | None = None
    embedding: list[float] | None = None


class RagUpsertRequest(_Strict):
    items: list[RagUpsertItem]


class RagDeleteRequest(_Strict):
    iris: list[str]


# ── 엔드포인트 ───────────────────────────────────────────────────────────────
@router.post("/rag/search", response_model=RagSearchResponse)
def rag_search(
    req: RagSearchRequest, retriever: ChromaRetriever = Depends(get_retriever)
) -> RagSearchResponse:
    try:
        hits = retriever.search(req.query, k=req.k, project_id=req.project_id)
    except Exception as exc:  # noqa: BLE001
        raise RagError(internal=f"검색 실패: {exc!r}") from exc
    return RagSearchResponse(
        hits=hits,
        sufficient=retriever.is_sufficient(hits),
        trace_id=get_trace_id(),
    )


@router.post("/rag/upsert")
def rag_upsert(
    req: RagUpsertRequest, retriever: ChromaRetriever = Depends(get_retriever)
) -> dict:
    try:
        n = retriever.upsert([it.model_dump() for it in req.items])
    except Exception as exc:  # noqa: BLE001
        raise RagError(internal=f"upsert 실패: {exc!r}") from exc
    return {"upserted": n, "trace_id": get_trace_id()}


@router.post("/rag/delete")
def rag_delete(
    req: RagDeleteRequest, retriever: ChromaRetriever = Depends(get_retriever)
) -> dict:
    try:
        n = retriever.delete(req.iris)
    except Exception as exc:  # noqa: BLE001
        raise RagError(internal=f"delete 실패: {exc!r}") from exc
    return {"deleted": n, "trace_id": get_trace_id()}


@router.get("/categories")
def categories(retriever: ChromaRetriever = Depends(get_retriever)) -> dict:
    try:
        stats = retriever.source.categories()
    except Exception as exc:  # noqa: BLE001
        raise RagError(internal=f"카테고리 집계 실패: {exc!r}") from exc
    return {
        "categories": [
            {"name": c.name, "sentences": c.sentences, "rules": c.rules} for c in stats
        ],
        "trace_id": get_trace_id(),
    }
