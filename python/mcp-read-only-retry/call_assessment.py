"""도구 호출 하나를 읽기인지 아닌지 판정하는 최소 평가기.

원본은 별도 패키지의 긴 규칙 집합이다. 여기서는 재시도 허가에 필요한 판단만 남겼다.
도구 이름은 ``origin__tool`` 형태이고, origin 이 호출을 노출한 서버다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

GATE_NONE = "none"
GATE_CONFIRM = "confirm"

NAME_SEPARATOR = "__"

# 읽기라고 주장해도 이름에 이런 동사가 있으면 주장을 믿지 않는다.
WRITE_VERBS = frozenset({
    "delete", "remove", "drop", "purge", "send", "post", "publish", "share",
    "create", "update", "modify", "edit", "write", "set", "put", "add",
    "insert", "replace", "upsert", "append", "move", "merge", "push",
    "upload", "cancel", "approve", "reply",
})

# camelCase 경계: 소문자나 숫자 뒤의 대문자, 그리고 연속 대문자 뒤에 소문자가 붙는 자리.
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

SENSITIVE_PATH_MARKERS = (
    ".ssh/", "id_rsa", "id_ed25519", ".env", ".aws/credentials",
    "credentials.json", ".netrc", "secrets.",
)


@dataclass(frozen=True)
class TrustPolicy:
    """호스트가 정한 신뢰 목록과 평가 스위치."""

    # 이 origin 의 annotation 을 믿는다.
    trusted_origins: tuple = ()
    # 설치 영수증으로 확인된 origin. 읽기 annotation 만 믿는다.
    read_verified_origins: tuple = ()
    enabled: bool = True
    verb_check: bool = True
    sensitive_path_check: bool = True
    # {도구 이름: {"gate": "none" | "confirm", "risk": "read" | ...}}
    tool_overrides: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Gate:
    kind: str
    risk: str = ""
    reason: str = ""


def _plain(text: str) -> str:
    """전각 문자와 제로폭 문자로 검사를 피하지 못하게 한다. 대소문자는 그대로 둔다."""
    folded = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")


def _normalize(text: str) -> str:
    return _plain(text).casefold()


def origin_of(tool_name: str) -> str:
    if NAME_SEPARATOR not in (tool_name or ""):
        return ""
    return tool_name.split(NAME_SEPARATOR, 1)[0]


def _name_tokens(tool_name: str) -> set:
    """소문자로 접기 전에 camelCase 경계(``sendEmail``, ``XMLSend``)를 나눈다."""
    spaced = _CAMEL_BOUNDARY.sub(" ", _plain(tool_name or ""))
    return {t for t in re.split(r"[^a-z0-9]+", spaced.casefold()) if t}


def has_write_verb(tool_name: str) -> bool:
    return not WRITE_VERBS.isdisjoint(_name_tokens(tool_name))


def _string_values(args: Any) -> list[str]:
    """중첩된 dict, list 안의 문자열까지 모두 모은다."""
    found: list[str] = []
    pending = [args]
    seen: set = set()
    while pending:
        node = pending.pop()
        if isinstance(node, str):
            found.append(node)
        elif isinstance(node, (dict, list, tuple, set, frozenset)):
            if id(node) in seen:
                continue
            seen.add(id(node))
            pending.extend(node.values() if isinstance(node, dict) else node)
    return found


def touches_sensitive_path(args: Any) -> bool:
    return any(
        marker in _normalize(text)
        for text in _string_values(args)
        for marker in SENSITIVE_PATH_MARKERS
    )


def assess_call(
    tool_name: str,
    args: dict,
    annotations: Optional[dict],
    *,
    policy: TrustPolicy,
) -> Gate:
    """GATE_NONE 과 risk "read" 가 함께 나올 때만 '읽기로 확인됨'이다."""
    if not policy.enabled:
        return Gate(GATE_NONE, reason="policy_disabled")

    override = policy.tool_overrides.get(tool_name) or {}
    if override.get("gate") in (GATE_NONE, GATE_CONFIRM):
        return Gate(override["gate"], risk=override.get("risk", ""), reason="override")

    origin = origin_of(tool_name)
    trusted = origin in policy.trusted_origins or origin in policy.read_verified_origins
    claims_read = bool((annotations or {}).get("readOnlyHint"))
    contradicted = policy.verb_check and claims_read and has_write_verb(tool_name)
    sensitive = policy.sensitive_path_check and touches_sensitive_path(args)

    if claims_read and trusted and not contradicted and not sensitive:
        return Gate(GATE_NONE, risk="read", reason="read_only")
    return Gate(GATE_CONFIRM, risk="unverified", reason="not_confirmed_read")
