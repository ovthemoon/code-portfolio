"""SQLite 에서 "읽고 나서 쓰는" 트랜잭션이 동시에 돌 때의 'database is locked'.

SQLite 의 기본 트랜잭션(DEFERRED)은 SELECT 로 읽기 스냅샷만 잡고 시작해서, 나중에
UPDATE 를 만나면 쓰기로 승격한다. 그 사이 다른 연결이 커밋하면 이 연결의 스냅샷은 낡았고,
SQLite 는 승격을 즉시 'database is locked' 로 거절한다. 이 거절에는 busy_timeout 이
적용되지 않는다. 기다려도 스냅샷은 새로워지지 않기 때문이다.

해법은 트랜잭션을 처음부터 쓰기로 시작하는 것이다(``BEGIN IMMEDIATE``). 쓰기 자리를 먼저
잡으려는 쪽은 busy_timeout 동안 줄을 서고, 자리를 얻은 뒤에 읽으므로 스냅샷이 낡을 수 없다.
그래도 몰려서 timeout 을 넘기면 마지막 방어로, 롤백한 뒤 지수 백오프와 지터로 통째로
다시 한다. 락은 트랜잭션 첫 문장에서 잡히므로 부분 커밋이 없어 다시 해도 안전하다.
"""

from __future__ import annotations

import logging
import random
import sqlite3
import time
from contextlib import contextmanager
from functools import wraps
from typing import Callable, Iterator, Optional

logger = logging.getLogger("sqlite_write_lock")

BUSY_TIMEOUT_MS = 5000
DB_LOCK_RETRIES = 4
DB_LOCK_BASE_DELAY = 0.05   # 50ms, 지수 백오프 + 지터

SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    id TEXT PRIMARY KEY,
    balance INTEGER NOT NULL,
    held INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS holds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id TEXT NOT NULL,
    amount INTEGER NOT NULL
);
"""


class InsufficientBalance(Exception):
    pass


def connect(path: str, *, busy_timeout_ms: int = BUSY_TIMEOUT_MS) -> sqlite3.Connection:
    """트랜잭션 제어를 직접 하는 연결. 암묵적 BEGIN 을 끄고(isolation_level=None) WAL 로 연다."""
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    return conn


def init_db(path: str, *, wallet_id: str, balance: int) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR REPLACE INTO wallets (id, balance, held) VALUES (?, ?, 0)", (wallet_id, balance))
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
    """``immediate`` 면 BEGIN IMMEDIATE(처음부터 쓰기), 아니면 기본 BEGIN(DEFERRED)."""
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")   # 여기서 실패하면 되돌릴 것이 없다
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def hold(conn: sqlite3.Connection, wallet_id: str, amount: int, *, immediate: bool = True,
         after_read: Optional[Callable[[], None]] = None) -> int:
    """잔액을 읽고, 충분하면 amount 만큼 잡아 두는 read-modify-write. hold id 를 돌려준다.

    ``after_read`` 는 읽은 직후 쓰기 전에 불리는 훅이다. 테스트가 이 틈에 다른 연결을
    끼워 넣어 겹침을 결정적으로 만든다.
    """
    with transaction(conn, immediate=immediate):
        balance, held = conn.execute("SELECT balance, held FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
        if balance < amount:
            raise InsufficientBalance(wallet_id)
        if after_read is not None:
            after_read()
        conn.execute("UPDATE wallets SET balance = ?, held = ? WHERE id = ?",
                     (balance - amount, held + amount, wallet_id))
        cursor = conn.execute("INSERT INTO holds (wallet_id, amount) VALUES (?, ?)", (wallet_id, amount))
        return cursor.lastrowid


def is_db_locked(exc: sqlite3.OperationalError) -> bool:
    return "database is locked" in str(exc).lower()


def retry_on_db_lock(fn=None, *, retries: int = DB_LOCK_RETRIES, base_delay: float = DB_LOCK_BASE_DELAY,
                     sleep: Callable[[float], None] = time.sleep,
                     jitter: Callable[[float, float], float] = random.uniform):
    """'database is locked' 이면 롤백하고 지수 백오프로 통째로 다시 하는 데코레이터.

    ``conn`` 키워드 인자가 있으면 재시도 사이에 그 연결을 롤백한다. 다른 오류는 그대로 올린다.
    횟수를 다 쓰면 마지막 예외를 올린다. ``sleep`` 과 ``jitter`` 는 테스트가 바꿔 끼운다.
    """

    def decorate(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            conn = kwargs.get("conn")
            last_exc: Optional[sqlite3.OperationalError] = None
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as exc:
                    if not is_db_locked(exc):
                        raise
                    last_exc = exc
                    if conn is not None and conn.in_transaction:
                        conn.execute("ROLLBACK")
                    if attempt == retries - 1:
                        break
                    delay = base_delay * (2 ** attempt) + jitter(0, base_delay)
                    logger.warning("database is locked, retry %d/%d in %.0fms (%s)",
                                   attempt + 1, retries - 1, delay * 1000, func.__name__)
                    sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapped

    return decorate(fn) if fn is not None else decorate
