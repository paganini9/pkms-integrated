"""06 퍼시스턴스 FastAPI 라우터 (내부, prefix 없음).

라우터 include 는 오케스트레이터가 main.py 에서 한다. 이 모듈은 스토어를 **import 시점에 열지 않는다**
(`get_store` 의존성으로 지연 개방). 에러는 schemas/errors.py 예외를 던지고, 본문 직렬화는
main.py 의 exception_handler 한 곳에서만 한다.
"""
from __future__ import annotations

from threading import Lock

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from core.config import settings
from core.logging import get_trace_id
from schemas.models import (
    KnowledgeScopeRequest,
    KnowledgeScopeResponse,
    Requirement,
    SaveRequest,
    SaveResponse,
)
from store.kg import KgService
from store.oxigraph import OxigraphStore
from store.projects import ProjectService

router = APIRouter()

# ── 지연 개방 싱글턴 (import 부작용 금지) ──────────────────────────────────
_store: OxigraphStore | None = None
_lock = Lock()


def get_store() -> OxigraphStore:
    """영속 스토어를 처음 요청 때 열고 시드를 멱등 적재한다."""
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                s = OxigraphStore(settings.oxigraph_path)
                paths = [p for p in settings.seed_ttl if p.exists()]
                if paths:
                    s.load_seed(paths)
                _store = s
    return _store


def get_kg(store: OxigraphStore = Depends(get_store)) -> KgService:
    return KgService(store)


def get_projects(store: OxigraphStore = Depends(get_store)) -> ProjectService:
    return ProjectService(store)


# ── 요청 모델(라우터 로컬) ─────────────────────────────────────────────────
class SparqlRequest(BaseModel):
    query: str = Field(min_length=1)


class DeleteRequest(BaseModel):
    iris: list[str] = Field(min_length=1)


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    target_vehicle: str
    knowledge_categories: list[str] = Field(min_length=1)
    target_env: str | None = None


class RequirementsRequest(BaseModel):
    requirements: list[Requirement]


# ── SPARQL (읽기 전용) ─────────────────────────────────────────────────────
@router.post("/sparql")
def sparql(req: SparqlRequest, store: OxigraphStore = Depends(get_store)) -> dict:
    rows = store.query(req.query, readonly=True)
    return {"rows": rows, "trace_id": get_trace_id()}


# ── KG 저장/삭제 (트리플+벡터 원자성) ─────────────────────────────────────
@router.post("/kg/save", status_code=status.HTTP_201_CREATED, response_model=SaveResponse)
def kg_save(req: SaveRequest, kg: KgService = Depends(get_kg)) -> SaveResponse:
    return kg.save(req)


@router.post("/kg/delete")
def kg_delete(req: DeleteRequest, kg: KgService = Depends(get_kg)) -> dict:
    deleted = kg.delete(req.iris)
    return {"deleted": deleted, "trace_id": get_trace_id()}


# ── 프로젝트 ──────────────────────────────────────────────────────────────
@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(req: CreateProjectRequest, projects: ProjectService = Depends(get_projects)) -> dict:
    return projects.create(
        name=req.name,
        target_vehicle=req.target_vehicle,
        knowledge_categories=req.knowledge_categories,
        target_env=req.target_env,
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str, projects: ProjectService = Depends(get_projects)) -> dict:
    return projects.get(project_id)


@router.put("/projects/{project_id}/knowledge-scope", response_model=KnowledgeScopeResponse)
def set_knowledge_scope(
    project_id: str,
    req: KnowledgeScopeRequest,
    projects: ProjectService = Depends(get_projects),
) -> KnowledgeScopeResponse:
    return projects.set_knowledge_scope(project_id, req.categories)


@router.post("/projects/{project_id}/requirements", status_code=status.HTTP_201_CREATED)
def add_requirements(
    project_id: str,
    req: RequirementsRequest,
    projects: ProjectService = Depends(get_projects),
) -> dict:
    return projects.add_requirements(project_id, req.requirements)
