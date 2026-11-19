"""발췌: 고아 크레딧 예치금(hold) 자동 회수. 원본 reclaim.py 를 거의 그대로 옮겼다.

SQLAlchemy 와 원본 모델이 필요해서 이 폴더에서는 실행하지 않는다.

서버 crash 등으로 채팅 스트림의 finally(정산 또는 환불)가 돌지 못한 hold 는 사용자 행의 held 에
영구히 남는다. 이 모듈이 TTL 이 지난(또는 전체) 미정산 hold 를 이미 있는 멱등 환불 함수로
돌려준다. 서버 시작 때 1회, 그리고 주기 태스크로 호출된다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from .db import session_scope
from .models import Hold

logger = logging.getLogger("reclaim")


async def reclaim_holds(*, ttl_minutes: Optional[int]) -> int:
    """미정산 hold 회수. ttl_minutes=None 이면 전체, 아니면 created_at < now-ttl 인 것만.

    각 hold 를 멱등 환불 함수로 돌려준다(이미 정산됐거나 환불됐거나 없으면 아무 일도 없다).
    회수를 시도한 건수를 돌려준다. 개별 환불 실패는 로그를 남기고 건너뛴다(치명적이지 않다).
    """
    from .chat import _perform_refund  # 지연 import: 순환을 피하고 import 시점 비용을 줄인다
    async with session_scope() as session:
        stmt = select(Hold.id)
        if ttl_minutes is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
            stmt = stmt.where(Hold.created_at < cutoff)
        hold_ids = [row[0] for row in (await session.execute(stmt)).all()]

    count = 0
    for hid in hold_ids:
        try:
            await _perform_refund(hid, "reclaimed: stale/orphaned hold")
            count += 1
        except Exception:  # noqa: BLE001
            logger.exception("[reclaim] refund failed hold=%s", hid)
    if count:
        logger.info("[reclaim] %d orphaned hold(s) refunded (ttl_minutes=%s)", count, ttl_minutes)
    return count


async def _loop(interval_seconds: int, ttl_minutes: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await reclaim_holds(ttl_minutes=ttl_minutes)
        except Exception:  # noqa: BLE001
            logger.exception("[reclaim] periodic sweep failed (continuing)")


def start_hold_reclaim_task(interval_minutes: int, ttl_minutes: int) -> asyncio.Task:
    """주기 회수 태스크 시작."""
    return asyncio.create_task(_loop(max(1, interval_minutes) * 60, ttl_minutes))


async def stop_hold_reclaim_task(task: asyncio.Task) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
