"""발췌: 결제 세션 행 잠금. 식별자는 일반 이름으로 바꿨다.

SQLAlchemy 와 원본 모델이 필요해서 이 폴더에서는 실행하지 않는다.
같은 아이디어를 표준 라이브러리로 줄여 실행하는 버전은 ../confirm_once.py 에 있다.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PaymentSession


async def lock_payment_session(session: AsyncSession, session_id: str) -> PaymentSession | None:
    """결제 세션 행의 최신값 + (Postgres) 행 잠금. 확정자(알림, 콜백, 복구 작업)가
    "이미 확정됐나"를 읽는 유일한 통로다.

    세 확정자는 중복 방지 키가 서로 다르다. 그래서 원장과 웹훅 로그가 두 확정자의 겹침을 못
    막는다. 세션 상태가 유일한 가드인데, 잠금 없이 읽으면 Postgres(READ COMMITTED)에서 두
    확정자가 같은 pending 을 동시에 보고 둘 다 적립한다(재현됨). 확정자는 상태를 판정하기
    전에 이 함수로 행을 잠가 직렬화하고, 이미 paid/refunded 면 건너뛴다. 잠금은 호출한
    트랜잭션이 끝날 때까지 유지된다. 순서는 항상 세션 행 -> 지갑 행이다(반대 순서로 잡는
    곳이 없어야 한다).

    populate_existing: 같은 세션이 이미 올린 행이면 identity map 이 옛 status 를 그대로
    돌려준다. 그러면 잠근 뒤의 재판정이 무의미해진다. SQLite 에는 ``FOR UPDATE`` 가 없지만
    BEGIN IMMEDIATE 가 이미 쓰기를 직렬화하므로 최신값 읽기만 한다. 없으면 None.
    """
    stmt = (
        select(PaymentSession)
        .where(PaymentSession.id == session_id)
        .execution_options(populate_existing=True)
    )
    if session.bind and session.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)
