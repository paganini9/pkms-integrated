"""로깅 · trace_id 전파 · 시크릿 마스킹."""
import logging
import re
import sys
import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")

# API 키 형태를 로그에서 지운다 (error_model.md §4)
_SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]+"),
    re.compile(r"(AIza[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]+"),
]


def mask_secrets(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub(r"\1***", text)
    return text


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def set_trace_id(value: str | None) -> str:
    tid = value or new_trace_id()
    _trace_id.set(tid)
    return tid


def get_trace_id() -> str:
    return _trace_id.get()


class _TraceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        record.msg = mask_secrets(str(record.msg))
        return True


def configure(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(trace_id)s] %(name)s: %(message)s"))
    handler.addFilter(_TraceFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
