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
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core import logging as applog
from core.config import settings
from rag.routes import router as rag_router
from reasoning.reasoner import reasoner_status
from reasoning.routes import router as reasoning_router
from schemas.errors import AppError
from schemas.models import HealthResponse
from store.routes import router as store_router

log = logging.getLogger("knowledge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    applog.configure(settings.log_level)
    log.info(
        "지식 서비스 기동 — embedding_provider=%s reasoner=%s",
        settings.embedding_provider,
        reasoner_status(),
    )
    _wire_layers()
    _bootstrap()
    yield
    log.info("지식 서비스 종료")


def _bootstrap() -> None:
    """기동 시 시드 멱등 적재 + 벡터 초기 인덱싱 (T-81 — 최초 기동만으로 6문장 조회).

    load_seed·ensure_indexed 는 모두 멱등이라 재기동에 안전하다. 실패해도 서비스 기동은 막지 않는다.
    """
    try:
        from store.routes import get_store

        store = get_store()  # 영속 스토어를 열고 시드를 멱등 적재
        log.info("시드 적재 완료 — 트리플 %d", store.triple_count())
    except Exception:  # noqa: BLE001 — 시드 적재 실패가 기동을 막지 않는다
        log.exception("시드 적재 실패")
    try:
        from rag.routes import get_retriever

        n = get_retriever().ensure_indexed()  # 6문장 벡터 초기 인덱싱(멱등)
        log.info("벡터 초기 인덱싱 완료 — %d 문장", n)
    except Exception:  # noqa: BLE001
        log.exception("벡터 초기 인덱싱 실패 — 검색은 첫 요청 때 지연 인덱싱")


def _wire_layers() -> None:
    """레이어 결선 — 오케스트레이터 소유 (각 Agent 는 자기 레이어만 만든다).

    03 RAG 의 `verified` 는 "그 문장의 규칙이 실제로 SHACL 게이트가 되었는가"여야 한다.
    기본값인 `MockRuleVerifier` 는 rules.ttl 에 존재하기만 하면 True 라 의미가 약하다.
    여기서 04 의 실제 규칙 컴파일러를 꽂아 준다(mock → 실구현 교체 = G1 조건).
    """
    from rag.routes import get_retriever
    from rag.verifier import CompiledRuleVerifier
    from reasoning.routes import get_compiler

    try:
        retriever = get_retriever()
        retriever.verifier = CompiledRuleVerifier(compiler=get_compiler())
        log.info("RAG verified 판정을 04 규칙 컴파일러에 연결")
    except Exception:  # noqa: BLE001 — 검색기 초기화 실패가 서비스 기동을 막지 않는다
        log.exception("RAG 결선 실패 — mock 검증기로 계속")


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


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI 기본 핸들러는 `{"detail": [...]}` 를 뱉는다 — 우리 에러 모델이 아니다.

    계약은 모든 에러 본문이 `{code, user_message, trace_id}` 이길 요구한다(error_model.md §1).
    이걸 덮지 않으면 05·07 이 두 가지 에러 형태를 다뤄야 한다.
    """
    trace_id = applog.get_trace_id()
    fields = [".".join(str(p) for p in err.get("loc", ()) if p != "body") for err in exc.errors()]
    log.warning("VALIDATION_ERROR: %s", exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "user_message": "입력값을 확인해 주세요.",
            "trace_id": trace_id,
            "details": {"fields": [f for f in fields if f]},
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """본문 파싱 실패(400)·404·405 등 프레임워크가 던지는 HTTP 예외도 계약 형태로 맞춘다."""
    trace_id = applog.get_trace_id()
    code = {400: "VALIDATION_ERROR", 404: "NOT_FOUND", 405: "VALIDATION_ERROR"}.get(exc.status_code, "INTERNAL")
    user_message = {
        "VALIDATION_ERROR": "입력값을 확인해 주세요.",
        "NOT_FOUND": "대상을 찾을 수 없습니다.",
        "INTERNAL": "일시적인 오류입니다.",
    }[code]
    log.warning("%s (%s): %s", code, exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code, content={"code": code, "user_message": user_message, "trace_id": trace_id}
    )


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
    # reasoner 는 JRE 부재 시 "no_jre" — owlrl 폴백으로 계속 동작한다. 숨기지 않는다.
    return HealthResponse(
        status="ok",
        store="ok",
        reasoner=reasoner_status(),
        rag="ok",  # 임베딩 모드(mock/st)는 기동 로그에 남긴다 — 계약 fixture 는 "ok"
        trace_id=applog.get_trace_id(),
    )


# ── 라우터 include (공유 파일 — 변경은 오케스트레이터 경유) ──
app.include_router(reasoning_router)  # 04: /validate/shacl · /reason/* · /satisfy · /rules/*
app.include_router(rag_router)  # 03: /rag/* · /categories
app.include_router(store_router)  # 06: /sparql · /kg/* · /projects*
