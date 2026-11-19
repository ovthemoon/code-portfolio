"""도구 호출에 시간 제한을 걸고, 죽은 세션을 버리고, 읽기 호출만 한 번 다시 하는 허브.

원본 mcp_client 의 호출 경로를 asyncio 만으로 줄여 다시 만들었다. 흐름은 같다.

1. 호출에 시간 제한을 둔다. 원격이 끊은 연결은 응답이 영영 오지 않는다.
2. 시간이 지나면 그 서버의 세션을 버린다. 다음 호출은 새로 연결한다.
3. 읽기로 확인된 호출만 새 연결에서 한 번 다시 한다. 쓰기는 원격이 이미 처리했을
   수 있어 다시 하면 효과가 두 번 난다.
4. 다시 연결한 뒤 도구 모양이 달라졌으면 재시도하지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Protocol

from read_retry_policy import retry_read_allowed

logger = logging.getLogger("resilient_tool_hub")

TOOL_CALL_TIMEOUT = 60.0


class ToolSession(Protocol):
    async def call_tool(self, name: str, args: dict[str, Any]) -> str: ...


@dataclass(frozen=True)
class ToolInfo:
    name: str                       # 노출 이름 "origin__raw"
    server_name: str
    raw_name: str
    input_schema: dict
    annotations: Optional[dict] = None


@dataclass(frozen=True)
class Connection:
    session: ToolSession
    # None 이면 도구 목록을 새로 받지 못한 것이다. 옛 목록은 재시도 권한이 아니다.
    tools: Optional[list[ToolInfo]] = None


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    text: str


ConnectFn = Callable[[str], Awaitable[Optional[Connection]]]


def _error(text: str) -> ToolResult:
    return ToolResult(False, text)


class ToolHub:
    def __init__(self, *, connect: ConnectFn, timeout: float = TOOL_CALL_TIMEOUT) -> None:
        self._connect = connect
        self._timeout = timeout
        self._sessions: dict[str, ToolSession] = {}
        self._tools: dict[str, ToolInfo] = {}

    def register(self, session: ToolSession, tools: list[ToolInfo]) -> None:
        for info in tools:
            self._sessions[info.server_name] = session
            self._tools[info.name] = info

    def has_session(self, server_name: str) -> bool:
        return server_name in self._sessions

    def _drop_session(self, server_name: str) -> None:
        self._sessions.pop(server_name, None)

    async def _call(self, session: ToolSession, info: ToolInfo, args: dict[str, Any]) -> ToolResult:
        text = await asyncio.wait_for(session.call_tool(info.raw_name, args), self._timeout)
        return ToolResult(True, text)

    async def call_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        info = self._tools.get(name)
        if info is None:
            return _error(f"unknown tool: {name}")
        session = self._sessions.get(info.server_name)
        if session is None:
            connection = await self._connect(info.server_name)
            if connection is None:
                return _error(f"cannot connect: {info.server_name}")
            self._adopt(info.server_name, connection)
            session = connection.session
            info = self._tools.get(name, info)

        # 시간이 지나 재연결한 뒤에 비교할 계약을 호출 시작 시점에 고정한다.
        retry_allowed = retry_read_allowed(name, args, info.annotations)
        contract = (info.server_name, info.raw_name, deepcopy(info.input_schema)) if retry_allowed else None
        try:
            return await self._call(session, info, args)
        except asyncio.TimeoutError:
            logger.warning("tool call timed out after %.0fs: %s", self._timeout, name)
            self._drop_session(info.server_name)
            if not retry_allowed:
                return _error(
                    f"tool timeout after {self._timeout:.0f}s: {name}. "
                    "Request again to reconnect."
                )
            return await self._retry_once(name, args, contract)
        except Exception as exc:  # noqa: BLE001
            logger.error("tool call failed (%s): %s", name, exc)
            return _error(f"tool error: {type(exc).__name__}: {exc}")

    async def _retry_once(self, name: str, args: dict[str, Any], contract: tuple) -> ToolResult:
        server_name = contract[0]
        connection = await self._connect(server_name)
        if connection is None:
            return _error(f"cannot reconnect: {server_name}")
        self._adopt(server_name, connection)

        refreshed = self._tools.get(name) if connection.tools is not None else None
        unchanged = (
            refreshed is not None
            and (refreshed.server_name, refreshed.raw_name, refreshed.input_schema) == contract
            and retry_read_allowed(name, args, refreshed.annotations)
        )
        if not unchanged:
            return _error(f"tool timeout; retry no longer authorized: {name}")
        try:
            return await self._call(connection.session, refreshed, args)
        except Exception as exc:  # noqa: BLE001 - 재시도까지 실패하면 오류 결과로 돌려준다
            logger.error("tool retry failed (%s): %s", name, exc)
            self._drop_session(server_name)
            return _error(f"tool error after retry: {type(exc).__name__}: {exc}")

    def _adopt(self, server_name: str, connection: Connection) -> None:
        self._sessions[server_name] = connection.session
        if connection.tools is None:
            return
        # 새 목록에 없는 도구는 사라진 것이다.
        self._tools = {
            tool_name: info for tool_name, info in self._tools.items()
            if info.server_name != server_name
        }
        for info in connection.tools:
            self._tools[info.name] = info
