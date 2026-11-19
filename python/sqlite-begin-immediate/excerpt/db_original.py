"""원본 서버 db.py 발췌. SQLAlchemy(async)가 필요해서 이 폴더에서는 실행하지 않는다.

실행되는 같은 아이디어의 표준 라이브러리 버전은 ../sqlite_write_lock.py 에 있다.
- retry_on_db_lock: 'database is locked' 이면 롤백하고 지수 백오프로 통째로 재시도
- _apply_sqlite_pragmas: pysqlite 의 암묵적 BEGIN 을 끄고, 'begin' 이벤트에서 BEGIN IMMEDIATE 를 발행
"""

import asyncio
import logging
import random
from functools import wraps

from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


# BEGIN IMMEDIATE + busy_timeout(5s) 로 동시 쓰기는 대부분 줄서서 처리되지만,
# 극단적으로 몰려(많은 사용자가 동시에 돈 쓰기) busy_timeout 을 넘기면 여전히
# OperationalError('database is locked') 가 날 수 있다. BEGIN IMMEDIATE 라 잠금은
# 트랜잭션 첫 문장에서 잡히므로 실패도 핸들러 첫 쿼리에서 드러나 부분 커밋이 없다.
# rollback 후 통째로 재시도해도 안전하다(멱등). 그래도 안 풀리면 마지막 예외를 올린다.
_DB_LOCK_RETRIES = 4
_DB_LOCK_BASE_DELAY = 0.05  # 50ms, 지수 백오프 + jitter


def _is_db_locked(exc: OperationalError) -> bool:
    return "database is locked" in str(exc).lower()


def retry_on_db_lock(fn):  # noqa: ANN001, ANN201
    """돈 경로 엔드포인트용. OperationalError('database is locked') 가 나면 트랜잭션을
    rollback 하고 지수 백오프로 재시도한다. FastAPI DI 는 __wrapped__ 시그니처를 따라가므로
    의존성 주입은 그대로 동작한다(session/ctx 는 kwargs 로 전달된다)."""

    @wraps(fn)
    async def _wrapped(*args, **kwargs):  # noqa: ANN002, ANN003
        session = kwargs.get("session")
        last_exc: OperationalError | None = None
        for attempt in range(_DB_LOCK_RETRIES):
            try:
                return await fn(*args, **kwargs)
            except OperationalError as exc:
                if not _is_db_locked(exc):
                    raise
                last_exc = exc
                if session is not None:
                    await session.rollback()
                if attempt == _DB_LOCK_RETRIES - 1:
                    break
                delay = _DB_LOCK_BASE_DELAY * (2**attempt) + random.uniform(
                    0, _DB_LOCK_BASE_DELAY
                )
                logger.warning(
                    "[db] database is locked — retry %d/%d in %.0fms (%s)",
                    attempt + 1, _DB_LOCK_RETRIES - 1, delay * 1000, fn.__name__,
                )
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    return _wrapped


def _apply_sqlite_pragmas(engine: AsyncEngine) -> None:
    """SQLite WAL + foreign keys + BEGIN IMMEDIATE 로 동시 쓰기 충돌 해소.

    왜 BEGIN IMMEDIATE 인가:
        pysqlite/aiosqlite 의 기본 트랜잭션은 DEFERRED 라 SELECT 는 읽기 잠금만 잡고
        시작하고, 이후 INSERT/UPDATE 로 승격한다. 두 요청(예: 캐릭터 여러 명에게 동시에
        대화해 hold 가 동시에 생기는 경우)이 같은 user 행을 read-modify-write 하면, 한쪽이
        쓰기로 승격하는 순간 다른 쪽 커밋으로 스냅샷이 낡아 SQLite 가 SQLITE_BUSY_SNAPSHOT 을
        '즉시' 반환한다. 이 승격 충돌에는 busy_timeout 이 적용되지 않아(데드락 회피상
        busy 핸들러 미호출) WAL+busy_timeout 만으로는 'database is locked' 가 났다.

        해법: pysqlite 의 암묵적 BEGIN 을 끄고(isolation_level=None) SQLAlchemy 의
        'begin' 이벤트에서 BEGIN IMMEDIATE 를 직접 발행한다. 트랜잭션이 시작부터 쓰기
        잠금(RESERVED)을 잡고, 충돌 시 즉시 실패하지 않고 busy_timeout(5s) 동안 기다리므로
        동시 hold 가 실패 없이 줄서서 처리된다. (read 트랜잭션도 쓰기 잠금을 잡아 다소
        직렬화되지만, 데스크톱 단일사용자 부하에선 정확성 이득이 훨씬 크다.)
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_conn, _connection_record) -> None:  # noqa: ANN001
        # pysqlite 가 트랜잭션을 자기 멋대로 BEGIN 하지 않게 한다. 트랜잭션 제어를
        # SQLAlchemy('begin' 이벤트)로 넘겨 BEGIN IMMEDIATE 를 쓸 수 있게 하려는 것이다.
        dbapi_conn.isolation_level = None
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(conn) -> None:  # noqa: ANN001
        # 모든 트랜잭션을 쓰기 잠금(RESERVED)으로 시작해 읽기에서 쓰기로 승격할 때의 충돌을 없앤다.
        conn.exec_driver_sql("BEGIN IMMEDIATE")

