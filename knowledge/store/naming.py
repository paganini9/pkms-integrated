"""T-92 — 라벨 → IRI 로컬네임 새니타이징.

저작이 만든 개념 라벨("오존 노출")을 그대로 IRI 에 이어붙이면 oxigraph 가 거부한다
(`ValueError: Invalid IRI code point ' '`) — 완전히 접지된 초안도 저장이 500 으로 죽었다.

원칙:
  · **표면형은 IRI 가 아니라 `rdfs:label` 이 보존한다.** IRI 는 식별자일 뿐이다.
  · **멱등** — 같은 라벨은 항상 같은 로컬네임.
  · **무손실 아니면 해시** — 새니타이징이 문자를 바꿨다면 라벨 해시를 접미해,
    서로 다른 라벨이 같은 IRI 로 뭉치지 않게 한다("오존 노출" ≠ "오존_노출").
  · 시드 IRI(WiperBlade·Rubber…)는 **여기 오지 않는다** — 어휘층에서 이미 해석되기 때문이다.
"""
from __future__ import annotations

import hashlib
import unicodedata

#: IRI 로컬 파트에서 쓰지 않는 문자(공백·구분자·예약문자). 이 밖의 유니코드 문자는 허용된다.
_UNSAFE = set(' \t\r\n<>"{}|^`\\%#/?[]:;,@&=+$!*\'()')


def _sanitize(label: str) -> str:
    normalized = unicodedata.normalize("NFC", label).strip()
    return "".join("_" if ch in _UNSAFE or ch.isspace() or ord(ch) < 0x20 else ch for ch in normalized)


def slug_localname(label: str) -> str:
    """개념 라벨 → IRI 로컬네임. 결정론·멱등.

    >>> slug_localname("오존")
    '오존'
    >>> slug_localname("오존 노출") == slug_localname("오존 노출")
    True
    >>> slug_localname("오존 노출") != slug_localname("오존_노출")
    True
    """
    safe = _sanitize(label)
    canonical = unicodedata.normalize("NFC", label).strip()
    if not safe or safe.strip("_") == "":
        return f"c_{_digest(canonical)}"
    if safe == canonical:
        return safe  # 무손실 — 해시 불필요
    # 손실 발생 → 원본 라벨 해시를 접미해 충돌을 막는다.
    return f"{safe}_{_digest(canonical)}"


def _digest(label: str) -> str:
    return hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]  # noqa: S324 — 식별자용(암호용 아님)
