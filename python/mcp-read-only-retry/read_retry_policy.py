"""재시도 허가는 호출자의 실행 컨텍스트에 묶인 호스트 권한이다.

도구가 스스로 단 annotation 은 힌트일 뿐 허가가 아니다. 이 모듈은 호출 하나가 시작될 때
호스트가 신뢰 목록을 스냅샷으로 넣어 두고, 재시도 직전에 같은 호출을 다시 평가한다.
스냅샷이 없으면 허가도 없다.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import Any, Iterator

from call_assessment import GATE_NONE, TrustPolicy, assess_call

_RETRY_SCOPE: ContextVar[TrustPolicy | None] = ContextVar("read_retry_scope", default=None)


def _origin_snapshot(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list, set, frozenset)):
        raise ValueError("invalid origin list")
    if any(not isinstance(origin, str) or not origin for origin in value):
        raise ValueError("invalid origin identity")
    return tuple(value)


@contextmanager
def read_retry_scope(policy: TrustPolicy | None) -> Iterator[None]:
    """이 실행의 호스트 신뢰를 스냅샷으로 고정한다. 없거나 깨졌으면 재시도 권한은 없다.

    연결 풀은 공유되므로 판단은 가변 전역 상태가 아니라 호출자의 async 컨텍스트를 따라야
    한다. 정책을 끄거나 도구별 override 를 넣어도, 바깥 효과가 어땠는지 모르는 작업을
    반복할 권한은 생기지 않도록 평가 스위치를 모두 켠 채로 굳힌다.
    """
    snapshot = None
    if isinstance(policy, TrustPolicy):
        try:
            snapshot = replace(
                policy,
                trusted_origins=_origin_snapshot(policy.trusted_origins),
                read_verified_origins=_origin_snapshot(policy.read_verified_origins),
                enabled=True,
                verb_check=True,
                sensitive_path_check=True,
                tool_overrides={},
            )
        except (TypeError, ValueError):
            snapshot = None
    token = _RETRY_SCOPE.set(snapshot)
    try:
        yield
    finally:
        _RETRY_SCOPE.reset(token)


def retry_read_allowed(tool_name: str, args: dict[str, Any], annotations: dict[str, Any] | None) -> bool:
    """호스트 신뢰와, 이 호출에 대해 방금 다시 한 읽기 평가를 모두 요구한다."""
    policy = _RETRY_SCOPE.get()
    if policy is None or not isinstance(tool_name, str) or "__" not in tool_name:
        return False
    if not isinstance(args, dict) or not isinstance(annotations, dict):
        return False
    if annotations.get("readOnlyHint") is not True or annotations.get("destructiveHint") is True:
        return False
    origin = tool_name.split("__", 1)[0]
    if not origin or origin not in (*policy.trusted_origins, *policy.read_verified_origins):
        return False
    try:
        decision = assess_call(tool_name, args, annotations, policy=policy)
        return decision.kind == GATE_NONE and decision.risk == "read"
    except Exception:  # noqa: BLE001 - 불확실하면 또 한 번의 바깥 효과를 허가하지 않는다
        return False
