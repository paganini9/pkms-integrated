"""테스트 부트스트랩 — rootdir 가 knowledge/ 라도 `rag`·`core`·`schemas` 를 import 하도록
knowledge 디렉터리를 sys.path 에 넣는다.
"""
import sys
from pathlib import Path

import pytest

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent
if str(KNOWLEDGE_DIR) not in sys.path:
    sys.path.insert(0, str(KNOWLEDGE_DIR))


def _clear_singletons() -> None:
    """엔진·컴파일러·검증기는 lru_cache 싱글턴이다 — 테스트 간에 살아남아 **남의 tmp 오버레이**를 문다."""
    from reasoning import routes as reasoning_routes
    from reasoning.causation import get_reifier

    for cached in (
        reasoning_routes.get_compiler,
        reasoning_routes.get_engine,
        reasoning_routes.get_spec_validator,
        reasoning_routes.get_upper_ontology,
        get_reifier,
    ):
        cached.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_authoring_overlay(tmp_path, monkeypatch):  # noqa: ANN001, ANN201
    """T-93 — 저작 규칙 오버레이는 테스트마다 격리한다.

    개발 `data/` 를 오염시키면 다음 테스트·개발 스토어의 판정이 달라진다(T-86 과 같은 병).
    """
    from core.config import settings

    monkeypatch.setattr(settings, "authoring_rules_path", tmp_path / "authoring_rules.ttl")
    _clear_singletons()
    yield
    _clear_singletons()
