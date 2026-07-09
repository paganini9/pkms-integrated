"""지식·추론 서비스 (FastAPI) — 내부 전용. 외부 노출은 BFF `/api/v1` 뿐이다.

레이어 규칙:
  · 여기(Python)만 RDF·SHACL·추론·RAG 를 안다.
  · 여기서 LLM 을 호출하지 않는다. 자연어 생성은 전부 BFF aiGateway.
  · 판정 필드(satisfies·conforms·violations)는 reasoner/SHACL 산출이다.

라우터 include 는 **공유 파일**이므로 변경은 오케스트레이터 경유 (interface_contracts.md §2).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core import logging as applog
from core.config import settings
from schemas.errors import AppError
from schemas.models import HealthResponse

log = logging.getLogger("knowledge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    applog.configure(settings.log_level)
    log.info("지식 서비스 기동 — embedding_mode=%s", settings.embedding_mode)
    # Phase 1: 06 이 시드 TTL 멱등 적재, 03 이 벡터 초기 인덱싱을 여기에 건다.
    yield
    log.info("지식 서비스 종료")


app = FastAPI(
    title="PKMS 지식·추론 서비스",
    version="0.1.0",
    description="내부 전용. Oxigraph · owlready2/HermiT · pySHACL · satisfy 엔진 · 규칙 컴파일러 · Chroma RAG",
    lifespan=lifespan,
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """CD-6 — X-Trace-Id 전파. 없으면 생성."""
    trace_id = applog.set_trace_id(request.headers.get("X-Trace-Id"))
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """응답 본문을 만드는 유일한 지점 (error_model.md §5). 내부 원인은 로그에만."""
    trace_id = applog.get_trace_id()
    log.warning("%s: %s", exc.code, exc.internal or "-")
    return JSONResponse(status_code=exc.http_status, content=exc.to_body(trace_id))


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = applog.get_trace_id()
    log.exception("처리되지 않은 예외")
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL", "user_message": "일시적인 오류입니다.", "trace_id": trace_id},
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    # Phase 1 에서 각 레이어가 실제 상태를 채운다. reasoner 는 JRE 부재 시 "no_jre"(owlrl 폴백).
    return HealthResponse(
        status="ok",
        store="ok",
        reasoner="no_jre",
        rag="ok",
        trace_id=applog.get_trace_id(),
    )


# ── 라우터 include (Phase 1 에서 각 Agent 가 채운다 — 오케스트레이터 경유) ──
# from store.routes import router as store_router          # 06: /sparql · /kg/* · /projects*
# from reasoning.routes import router as reasoning_router  # 04: /validate/shacl · /reason/* · /satisfy · /rules/*
# from rag.routes import router as rag_router              # 03: /rag/*
# app.include_router(store_router)
# app.include_router(reasoning_router)
# app.include_router(rag_router)
