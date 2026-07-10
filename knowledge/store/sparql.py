"""읽기 전용 SPARQL 게이트 — `/sparql` 은 계약상 읽기 전용이다.

`assert_readonly` 는 **주석 제거 + 문자열/IRI 마스킹** 후 (PREFIX·BASE 를 건너뛴)
첫 유효 키워드로 판정한다. 그래서 `# DELETE ...`(주석)나
`"INSERT DATA"`(리터럴) 같은 우회는 통과하고, 실제 update 절만 거부한다.

이 게이트는 1차 방어선이다. 2차 방어선은 `OxigraphStore.query()` 가
`store.query()`(읽기 전용 실행기)만 쓰고 `store.update()` 를 절대 호출하지 않는다는 점이다.
"""
import re

from schemas.errors import ValidationError

# 읽기 전용으로 허용되는 쿼리 형식
_READ_KEYWORDS = {"SELECT", "ASK", "CONSTRUCT", "DESCRIBE"}
# SPARQL 1.1 Update 키워드 — 전부 거부
_UPDATE_KEYWORDS = {
    "INSERT", "DELETE", "LOAD", "CLEAR", "DROP", "CREATE", "COPY", "MOVE", "ADD", "WITH",
}

# 선두의 PREFIX/BASE 선언 (IRI 는 이미 _IRI_ 로 마스킹된 상태)
_PROLOGUE = re.compile(r"^\s*(?:PREFIX\s+\S*\s*_IRI_|BASE\s*_IRI_)", re.IGNORECASE)
_FIRST_WORD = re.compile(r"[A-Za-z]+")


def _mask(query: str) -> str:
    """주석을 제거하고 문자열 리터럴·IRI 를 placeholder 로 치환한다.

    이렇게 하면 주석/리터럴/IRI 안에 들어있는 update 키워드가 판정에 영향을 주지 않는다.
    """
    out: list[str] = []
    i, n = 0, len(query)
    while i < n:
        c = query[i]
        # 한 줄 주석 — '#' 부터 줄 끝까지 (문자열/IRI 밖에서만 여기 도달)
        if c == "#":
            while i < n and query[i] not in "\r\n":
                i += 1
            continue
        # IRI 참조 <...> — 내부의 '#'(예: domain#S1)이 주석으로 오인되지 않게 통째로 마스킹
        if c == "<":
            j = i + 1
            while j < n and query[j] not in ">\r\n":
                j += 1
            out.append(" _IRI_ ")
            i = j + 1 if j < n else j
            continue
        # 문자열 리터럴 — '...', "...", 삼중따옴표 지원
        if c in "\"'":
            quote = c
            if query[i:i + 3] == quote * 3:
                end = query.find(quote * 3, i + 3)
                i = end + 3 if end != -1 else n
            else:
                j = i + 1
                while j < n:
                    if query[j] == "\\":
                        j += 2
                        continue
                    if query[j] == quote or query[j] in "\r\n":
                        break
                    j += 1
                i = j + 1
            out.append(" _STR_ ")
            continue
        out.append(c)
        i += 1
    return "".join(out)


def is_readonly(query: str) -> bool:
    """읽기 전용이면 True. (assert_readonly 의 비예외 버전)"""
    s = _mask(query)
    # 선두 PREFIX/BASE 선언 반복 제거
    while True:
        m = _PROLOGUE.match(s)
        if not m:
            break
        s = s[m.end():]
    m = _FIRST_WORD.search(s)
    if not m:
        return False
    return m.group(0).upper() in _READ_KEYWORDS


def assert_readonly(query: str) -> None:
    """읽기 전용이 아니면 `ValidationError` 를 던진다.

    SELECT/ASK/CONSTRUCT/DESCRIBE 만 허용. INSERT/DELETE/LOAD/CLEAR/DROP/CREATE/COPY/MOVE/ADD/WITH 는 거부.
    """
    s = _mask(query)
    while True:
        m = _PROLOGUE.match(s)
        if not m:
            break
        s = s[m.end():]
    m = _FIRST_WORD.search(s)
    kw = m.group(0).upper() if m else ""
    if kw in _READ_KEYWORDS:
        return
    if kw in _UPDATE_KEYWORDS:
        raise ValidationError(
            internal=f"readonly gate: update keyword '{kw}' rejected",
            user_message="이 엔드포인트는 읽기 전용입니다. SELECT/ASK/CONSTRUCT/DESCRIBE 만 허용됩니다.",
        )
    raise ValidationError(
        internal=f"readonly gate: no valid read keyword (got '{kw or '∅'}')",
        user_message="유효한 읽기 전용 SPARQL 쿼리가 아닙니다.",
    )
