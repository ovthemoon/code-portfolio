"""동시 hold 회귀 테스트: 읽고 쓰는 트랜잭션이 겹쳐도 'database is locked' 없이 줄을 선다.

재현은 결정적이다. DEFERRED 승격 실패는 스레드 경합에 기대지 않고 두 연결을 순서대로 조작해
만든다(A 가 읽는다, B 가 커밋한다, A 가 쓰려 한다). BEGIN IMMEDIATE 쪽은 한 연결이 쓰기 자리를
쥐고 있는 동안 다른 스레드가 줄을 서는 것을 보이고, 몰아치는 경우는 결과 불변식만 확인한다.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from sqlite_write_lock import InsufficientBalance, connect, hold, init_db, retry_on_db_lock

WALLET = "w1"
SEED = 1000


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "wallet.db")
    init_db(path, wallet_id=WALLET, balance=SEED)
    return path


def read_wallet(path):
    conn = connect(path)
    try:
        balance, held = conn.execute("SELECT balance, held FROM wallets WHERE id = ?", (WALLET,)).fetchone()
        rows = conn.execute("SELECT COUNT(*) FROM holds WHERE wallet_id = ?", (WALLET,)).fetchone()[0]
        return balance, held, rows
    finally:
        conn.close()


# DEFERRED 승격은 busy_timeout 이 있어도 즉시 실패한다

def test_deferred_read_then_write_fails_immediately_despite_busy_timeout(db_path):
    a = connect(db_path, busy_timeout_ms=3000)
    b = connect(db_path, busy_timeout_ms=3000)
    try:
        a.execute("BEGIN")
        a.execute("SELECT balance FROM wallets WHERE id = ?", (WALLET,)).fetchone()   # A 가 스냅샷을 잡는다
        hold(b, WALLET, 100, immediate=False)                                         # B 가 그 뒤에 커밋한다

        started = time.monotonic()
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            a.execute("UPDATE wallets SET balance = 0 WHERE id = ?", (WALLET,))      # A 의 스냅샷은 낡았다
        elapsed = time.monotonic() - started

        assert elapsed < 1.0, "busy_timeout(3s) 을 기다리지 않고 바로 실패해야 한다"
    finally:
        a.close()
        b.close()


def test_a_failed_upgrade_loses_nothing(db_path):
    """실패한 쪽의 쓰기는 반영되지 않고, 성공한 쪽의 쓰기는 보존된다."""
    a = connect(db_path)
    b = connect(db_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            hold(a, WALLET, 50, immediate=False,
                 after_read=lambda: hold(b, WALLET, 100, immediate=False))
        assert not a.in_transaction
    finally:
        a.close()
        b.close()
    assert read_wallet(db_path) == (SEED - 100, 100, 1)


# BEGIN IMMEDIATE 는 줄을 서서 통과한다

def test_immediate_transaction_waits_for_the_write_lock_and_then_succeeds(db_path):
    holder = connect(db_path)
    outcome: dict = {}
    started = threading.Event()

    def run_waiter():
        conn = connect(db_path)
        try:
            t0 = time.monotonic()
            started.set()
            outcome["hold_id"] = hold(conn, WALLET, 50, immediate=True)   # 쓰기 자리가 날 때까지 기다린다
            outcome["waited"] = time.monotonic() - t0
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc
        finally:
            conn.close()

    try:
        holder.execute("BEGIN IMMEDIATE")                     # 쓰기 자리를 먼저 쥔다
        thread = threading.Thread(target=run_waiter)
        thread.start()
        started.wait(timeout=5)
        time.sleep(0.2)                                       # 대기자가 줄을 서 있는 구간
        holder.execute("UPDATE wallets SET balance = balance - 100, held = held + 100 WHERE id = ?", (WALLET,))
        holder.execute("COMMIT")
        thread.join(timeout=10)
    finally:
        holder.close()

    assert "error" not in outcome, outcome.get("error")
    assert outcome["waited"] >= 0.15
    # 대기자는 쓰기 자리를 얻은 뒤에 읽었으므로 holder 의 커밋이 보인다.
    assert read_wallet(db_path) == (SEED - 100 - 50, 150, 1)


def run_concurrent_holds(db_path, *, count: int, amount: int, immediate: bool):
    barrier = threading.Barrier(count)
    results: list = [None] * count

    def worker(index: int) -> None:
        conn = connect(db_path)
        try:
            barrier.wait(timeout=10)
            hold(conn, WALLET, amount, immediate=immediate)
            results[index] = "ok"
        except sqlite3.OperationalError as exc:
            results[index] = str(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_concurrent_immediate_holds_all_succeed_and_the_ledger_balances(db_path):
    count, amount = 10, 50
    results = run_concurrent_holds(db_path, count=count, amount=amount, immediate=True)

    assert results == ["ok"] * count, results
    assert read_wallet(db_path) == (SEED - count * amount, count * amount, count)


def test_concurrent_deferred_holds_never_lose_an_update(db_path):
    """실패는 허용하지만 조용한 덮어쓰기는 없다. 성공한 개수만큼만 잔액이 줄어 있어야 한다."""
    count, amount = 10, 50
    results = run_concurrent_holds(db_path, count=count, amount=amount, immediate=False)

    succeeded = results.count("ok")
    failures = [r for r in results if r != "ok"]
    assert all("database is locked" in r for r in failures), failures
    assert read_wallet(db_path) == (SEED - succeeded * amount, succeeded * amount, succeeded)


def test_insufficient_balance_rolls_back_and_leaves_the_connection_usable(db_path):
    conn = connect(db_path)
    try:
        with pytest.raises(InsufficientBalance):
            hold(conn, WALLET, SEED + 1)
        assert not conn.in_transaction
        hold(conn, WALLET, 10)
    finally:
        conn.close()
    assert read_wallet(db_path) == (SEED - 10, 10, 1)


def test_retry_succeeds_after_a_real_stale_snapshot_failure(db_path):
    """DEFERRED 승격 실패를 실제로 만들고, 재시도가 새 스냅샷으로 통째로 다시 해서 성공한다."""
    a = connect(db_path)
    b = connect(db_path)
    competing = {"pending": True}

    def interleave():
        if competing["pending"]:                 # 첫 시도에서만 다른 연결이 끼어든다
            competing["pending"] = False
            hold(b, WALLET, 100, immediate=False)

    @retry_on_db_lock(sleep=lambda _s: None)
    def hold_with_retry(*, conn):
        return hold(conn, WALLET, 50, immediate=False, after_read=interleave)

    try:
        hold_with_retry(conn=a)
    finally:
        a.close()
        b.close()

    assert read_wallet(db_path) == (SEED - 100 - 50, 150, 2)


def locked_error() -> sqlite3.OperationalError:
    return sqlite3.OperationalError("database is locked")


def test_retry_backs_off_exponentially_with_jitter():
    sleeps: list = []
    calls = {"n": 0}

    @retry_on_db_lock(base_delay=0.05, sleep=sleeps.append, jitter=lambda lo, hi: hi)
    def flaky():
        calls["n"] += 1
        if calls["n"] <= 2:
            raise locked_error()
        return "done"

    assert flaky() == "done"
    assert calls["n"] == 3
    assert sleeps == pytest.approx([0.05 * 1 + 0.05, 0.05 * 2 + 0.05])


def test_retry_gives_up_after_the_limit_and_raises_the_last_error():
    sleeps: list = []
    calls = {"n": 0}

    @retry_on_db_lock(retries=4, sleep=sleeps.append, jitter=lambda lo, hi: 0.0)
    def always_locked():
        calls["n"] += 1
        raise locked_error()

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        always_locked()
    assert calls["n"] == 4
    assert len(sleeps) == 3          # 마지막 시도 뒤에는 기다리지 않는다


def test_other_operational_errors_are_not_retried():
    calls = {"n": 0}

    @retry_on_db_lock(sleep=lambda _s: None)
    def broken_sql():
        calls["n"] += 1
        raise sqlite3.OperationalError("no such table: nope")

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        broken_sql()
    assert calls["n"] == 1


def test_retry_rolls_back_the_open_transaction_between_attempts(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    conn.executescript("CREATE TABLE t (v INTEGER)")
    calls = {"n": 0}

    @retry_on_db_lock(sleep=lambda _s: None)
    def insert_then_maybe_fail(*, conn):
        calls["n"] += 1
        conn.execute("BEGIN")
        conn.execute("INSERT INTO t VALUES (1)")
        if calls["n"] == 1:
            raise locked_error()          # 트랜잭션이 열린 채로 실패한다
        conn.execute("COMMIT")

    insert_then_maybe_fail(conn=conn)

    assert calls["n"] == 2
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1    # 첫 시도의 삽입은 남지 않았다
    conn.close()


def test_retry_decorator_works_without_arguments():
    calls = {"n": 0}

    @retry_on_db_lock
    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise locked_error()
        return "ok"

    assert flaky() == "ok"      # 기본 백오프(50ms 안팎)만큼만 기다린다
    assert calls["n"] == 2
