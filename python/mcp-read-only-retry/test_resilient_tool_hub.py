"""시간 제한, 죽은 세션 폐기, 읽기 호출 한 번 재시도.

증상: 원격이 유휴 연결을 끊었는데 클라이언트는 그것을 모르고 응답을 기다렸다.
도구 호출에 시간 제한이 없어 호출이 끝나지 않았다.
"""

import asyncio
from dataclasses import replace

import pytest

from call_assessment import TrustPolicy
from read_retry_policy import read_retry_scope
from resilient_tool_hub import Connection, ToolHub, ToolInfo

TIMEOUT = 0.05


class HangingSession:
    """응답하지 않는 세션. 끊긴 연결을 흉내 낸다."""

    def __init__(self) -> None:
        self.calls = 0

    async def call_tool(self, name, args):
        self.calls += 1
        await asyncio.Event().wait()


class OkSession:
    def __init__(self, text: str = "ok") -> None:
        self.calls = 0
        self._text = text

    async def call_tool(self, name, args):
        self.calls += 1
        return self._text


def make_info(*, read_only: bool, schema=None) -> ToolInfo:
    return ToolInfo(
        name="srv__do", server_name="srv", raw_name="do",
        input_schema=schema if schema is not None else {},
        annotations={"readOnlyHint": True} if read_only else None,
    )


def make_hub(session, *, read_only: bool, connect=None, timeout=TIMEOUT):
    async def refuse(server_name):
        raise AssertionError("재연결하면 안 되는 경로에서 재연결을 시도했다")

    hub = ToolHub(connect=connect or refuse, timeout=timeout)
    info = make_info(read_only=read_only)
    hub.register(session, [info])
    return hub, info


TRUSTED = TrustPolicy(trusted_origins=("srv",))


def run(coro):
    return asyncio.run(coro)


def test_write_tool_times_out_and_is_not_retried():
    """쓰기 도구는 재시도 금지. 원격이 이미 처리했을 수 있다."""
    session = HangingSession()
    hub, _ = make_hub(session, read_only=False)

    result = run(hub.call_tool("srv__do", {}))

    assert not result.ok
    assert "timeout" in result.text
    assert session.calls == 1


def test_timeout_drops_the_session_so_the_next_call_reconnects():
    hub, _ = make_hub(HangingSession(), read_only=False)

    run(hub.call_tool("srv__do", {}))

    assert not hub.has_session("srv"), "죽은 세션이 남으면 다음 호출도 같이 멈춘다"


def test_read_only_tool_retries_once_after_reconnect():
    fresh = OkSession("3 events")

    async def reconnect(server_name):
        return Connection(fresh, [make_info(read_only=True)])

    hub, _ = make_hub(HangingSession(), read_only=True, connect=reconnect)

    async def scenario():
        with read_retry_scope(TRUSTED):
            return await hub.call_tool("srv__do", {})

    result = run(scenario())

    assert result.ok and result.text == "3 events"
    assert fresh.calls == 1


def test_retry_failure_is_surfaced_instead_of_hanging():
    async def reconnect_to_another_dead_one(server_name):
        return Connection(HangingSession(), [make_info(read_only=True)])

    hub, _ = make_hub(HangingSession(), read_only=True, connect=reconnect_to_another_dead_one)

    async def scenario():
        with read_retry_scope(TRUSTED):
            return await asyncio.wait_for(hub.call_tool("srv__do", {}), 5)

    result = run(scenario())

    assert not result.ok
    assert "after retry" in result.text
    assert not hub.has_session("srv")


def test_healthy_call_is_unaffected_by_the_timeout():
    session = OkSession("fine")
    hub, _ = make_hub(session, read_only=True, timeout=5.0)

    result = run(hub.call_tool("srv__do", {}))

    assert result.ok and result.text == "fine"
    assert session.calls == 1
    assert hub.has_session("srv")


def test_unverified_read_hint_does_not_repeat_the_effect():
    """검증되지 않은 서버의 읽기 주장은 두 번째 바깥 효과의 근거가 아니다."""
    effects = []

    class EffectThenHang(HangingSession):
        async def call_tool(self, name, args):
            effects.append("effect")
            await super().call_tool(name, args)

    fresh = OkSession()

    async def reconnect(server_name):
        return Connection(fresh, [make_info(read_only=True)])

    hub, _ = make_hub(EffectThenHang(), read_only=True, connect=reconnect)

    result = run(hub.call_tool("srv__do", {}))  # 호스트 신뢰 스냅샷이 없다

    assert "timeout" in result.text
    assert effects == ["effect"]
    assert fresh.calls == 0


@pytest.mark.parametrize("change", ["removed", "write", "schema", "identity"])
def test_reconnect_must_not_repeat_a_changed_or_removed_tool(change):
    original = make_info(read_only=True)
    fresh = OkSession()
    changed = {
        "removed": [],
        "write": [replace(original, annotations={"readOnlyHint": False})],
        "schema": [replace(original, input_schema={"type": "object", "required": ["path"]})],
        "identity": [replace(original, raw_name="different")],
    }[change]

    async def reconnect(server_name):
        return Connection(fresh, changed)

    hub, _ = make_hub(HangingSession(), read_only=True, connect=reconnect)

    async def scenario():
        with read_retry_scope(TrustPolicy(read_verified_origins=("srv",))):
            return await hub.call_tool("srv__do", {})

    result = run(scenario())

    assert "retry no longer authorized" in result.text
    assert fresh.calls == 0


def test_stale_catalog_after_reconnect_cannot_authorize_retry():
    """도구 목록을 새로 받지 못했다면 옛 목록으로 재시도를 허가하지 않는다."""
    fresh = OkSession()

    async def reconnect(server_name):
        return Connection(fresh, None)

    original = HangingSession()
    hub, _ = make_hub(original, read_only=True, connect=reconnect)

    async def scenario():
        with read_retry_scope(TRUSTED):
            return await hub.call_tool("srv__do", {})

    result = run(scenario())

    assert not result.ok
    assert original.calls == 1
    assert fresh.calls == 0


def test_failed_reconnect_is_reported():
    async def cannot_connect(server_name):
        return None

    hub, _ = make_hub(HangingSession(), read_only=True, connect=cannot_connect)

    async def scenario():
        with read_retry_scope(TRUSTED):
            return await hub.call_tool("srv__do", {})

    result = run(scenario())

    assert not result.ok
    assert "reconnect" in result.text


def test_unknown_tool_is_an_error_result_not_an_exception():
    hub, _ = make_hub(OkSession(), read_only=True)

    result = run(hub.call_tool("srv__missing", {}))

    assert not result.ok
