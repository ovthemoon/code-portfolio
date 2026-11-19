"""결제 확정자 셋이 같은 결제를 동시에 확정해도 적립은 한 번만 한다.

결제가 끝나면 세 곳이 각자 "확정"을 시도한다. 결제사의 알림, 결제 화면의 콜백, 놓친 결제를
찾아내는 복구 작업이다. 셋의 중복 방지 키는 서로 다르다. 그래서 원장의 유니크 제약이 겹침을
막지 못한다. 막을 수 있는 것은 결제 세션의 상태뿐인데, 잠금 없이 읽고 판정하면 두 확정자가
같은 pending 을 동시에 보고 둘 다 적립한다.

해법은 판정 전에 세션 행을 잠그고, 잠금 아래에서 최신 상태를 다시 읽는 것이다. 이미 확정됐으면
건너뛴다. 원본은 Postgres 의 ``SELECT ... FOR UPDATE`` 를 쓴다. SQLite 에는 행 잠금이 없고
``BEGIN IMMEDIATE`` 가 쓰기 전체를 직렬화하므로, 여기서는 같은 아이디어를 그것으로 옮겼다.

- ``confirm_with_lock``: 잠그고 읽고 판정한다(고친 쪽).
- ``confirm_without_lock``: 잠금 없이 읽고, 쓰기 직전에 다시 확인하지 않는다(고치기 전).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

STATUS_PENDING = "pending"
STATUS_PAID = "paid"
STATUS_REFUNDED = "refunded"

CONFIRMERS = ("notification", "callback", "reconciler")

SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_sessions (
    id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL,
    units INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    idem_key TEXT NOT NULL UNIQUE,
    delta INTEGER NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(path: str) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def create_session(conn: sqlite3.Connection, session_id: str, wallet_id: str, units: int) -> None:
    conn.execute("INSERT INTO payment_sessions (id, wallet_id, units) VALUES (?, ?, ?)",
                 (session_id, wallet_id, units))


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """처음부터 쓰기 자리를 잡는 트랜잭션."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def lock_payment_session(conn: sqlite3.Connection, session_id: str) -> Optional[tuple]:
    """세션 행의 최신값: (wallet_id, units, status). 없으면 None.

    확정자가 "이미 확정됐나"를 읽는 유일한 통로다. 호출자는 쓰기 트랜잭션 안에 있어야 한다.
    트랜잭션 밖에서 읽으면 잠금이 아니라 그냥 낡을 수 있는 읽기다.
    """
    if not conn.in_transaction:
        raise RuntimeError("lock_payment_session must run inside a write transaction")
    return conn.execute(
        "SELECT wallet_id, units, status FROM payment_sessions WHERE id = ?", (session_id,)
    ).fetchone()


def _has_original_grant(conn: sqlite3.Connection, session_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM ledger WHERE session_id = ? AND delta > 0 LIMIT 1", (session_id,)
    ).fetchone() is not None


def already_fulfilled(conn: sqlite3.Connection, session_id: str) -> bool:
    """이 결제가 이미 확정됐는데 또 적립하려 하면 True(건너뛴다).

    paid 는 확정이다. refunded 도 확정이다. 단 원래의 적립이 있을 때만이다. 환불이 결제보다
    먼저 도착한 순서 역전(적립 없이 환불만 -N)은, 늦게 온 결제가 적립해서 같은 지갑에서 상쇄돼야
    하므로 막지 않는다.
    """
    row = conn.execute("SELECT status FROM payment_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None or row[0] not in (STATUS_PAID, STATUS_REFUNDED):
        return False
    if row[0] == STATUS_REFUNDED and not _has_original_grant(conn, session_id):
        return False
    return True


def grant(conn: sqlite3.Connection, session_id: str, confirmer: str,
           wallet_id: str, units: int) -> bool:
    """적립 한 줄과 상태 갱신. 확정자마다 키가 다르다. 같은 확정자의 재전송만 키로 막힌다."""
    cursor = conn.execute(
        "INSERT OR IGNORE INTO ledger (wallet_id, session_id, idem_key, delta) VALUES (?, ?, ?, ?)",
        (wallet_id, session_id, f"{confirmer}:{session_id}", units),
    )
    if cursor.rowcount == 0:
        return False
    conn.execute(
        "UPDATE payment_sessions SET status = CASE WHEN status = ? THEN status ELSE ? END WHERE id = ?",
        (STATUS_REFUNDED, STATUS_PAID, session_id),
    )
    return True


def confirm_with_lock(conn: sqlite3.Connection, session_id: str, confirmer: str,
                      pause: Optional[Callable[[], None]] = None) -> bool:
    """먼저 쓰기 자리를 잡고, 그 아래에서 최신 상태를 읽어 판정한다. 적립했으면 True."""
    with transaction(conn):
        row = lock_payment_session(conn, session_id)
        if row is None or already_fulfilled(conn, session_id):
            return False
        if pause is not None:
            pause()
        wallet_id, units, _status = row
        return grant(conn, session_id, confirmer, wallet_id, units)


def confirm_without_lock(conn: sqlite3.Connection, session_id: str, confirmer: str,
                         pause: Optional[Callable[[], None]] = None) -> bool:
    """고치기 전. 잠금 없이 상태를 읽고, 쓰기 직전에 다시 확인하지 않는다.

    읽은 값은 쓰는 시점에 낡을 수 있다(읽기 커밋 격리에서 다른 확정자가 그 사이에 커밋한 경우와
    같다). ``pause`` 는 읽은 뒤 쓰기 전에 불리는 훅으로, 테스트가 겹침을 결정적으로 만든다.
    """
    row = conn.execute(
        "SELECT wallet_id, units, status FROM payment_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None or already_fulfilled(conn, session_id):
        return False
    if pause is not None:
        pause()
    with transaction(conn):
        wallet_id, units, _status = row
        return grant(conn, session_id, confirmer, wallet_id, units)


def refund(conn: sqlite3.Connection, session_id: str) -> bool:
    """환불 한 줄과 상태 갱신. 이미 환불됐으면 건너뛴다(멱등)."""
    with transaction(conn):
        row = lock_payment_session(conn, session_id)
        if row is None or row[2] == STATUS_REFUNDED:
            return False
        wallet_id, units, _status = row
        conn.execute(
            "INSERT OR IGNORE INTO ledger (wallet_id, session_id, idem_key, delta) VALUES (?, ?, ?, ?)",
            (wallet_id, session_id, f"refund:{session_id}", -units),
        )
        conn.execute("UPDATE payment_sessions SET status = ? WHERE id = ?", (STATUS_REFUNDED, session_id))
        return True


def wallet_total(conn: sqlite3.Connection, wallet_id: str) -> int:
    return conn.execute(
        "SELECT COALESCE(SUM(delta), 0) FROM ledger WHERE wallet_id = ?", (wallet_id,)
    ).fetchone()[0]


def grant_count(conn: sqlite3.Connection, session_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM ledger WHERE session_id = ? AND delta > 0", (session_id,)
    ).fetchone()[0]
