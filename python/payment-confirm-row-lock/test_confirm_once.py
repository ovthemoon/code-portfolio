"""확정자(알림, 콜백, 복구 작업)가 겹쳐도 적립은 한 번. 판정은 잠금 아래에서 다시 읽어야 한다.

적립 수치(UNITS)는 예시값이다. 겹침은 결정적으로 만든다. 잠금 없는 쪽은 세 스레드가 모두 읽은
뒤에야 쓰도록 장벽을 두고, 잠금 있는 쪽은 쓰기 자리를 쥔 채 잠깐 멈춰 다른 둘이 줄을 서게 한다.
"""

from __future__ import annotations

import threading
import time

import pytest

import confirm_once as co
from confirm_once import CONFIRMERS, STATUS_PAID, STATUS_PENDING, STATUS_REFUNDED

WALLET = "wallet-1"
UNITS = 10      # 예시값


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "payments.db")
    co.init_db(path)
    return path


def new_session(db_path, session_id="s1"):
    conn = co.connect(db_path)
    try:
        co.create_session(conn, session_id, WALLET, UNITS)
    finally:
        conn.close()
    return session_id


def snapshot(db_path, session_id="s1"):
    conn = co.connect(db_path)
    try:
        status = conn.execute("SELECT status FROM payment_sessions WHERE id = ?", (session_id,)).fetchone()[0]
        return status, co.grant_count(conn, session_id), co.wallet_total(conn, WALLET)
    finally:
        conn.close()


def run_confirmers(db_path, session_id, confirm, *, hold_open):
    """세 확정자를 동시에 출발시킨다. 각자 자기 연결과 자기 중복 방지 키를 쓴다.

    ``hold_open=False`` 는 잠금 없는 확정자 전용이다(셋이 모두 읽을 때까지 장벽에서 기다린다).
    잠금 아래에서 장벽을 기다리면 줄 선 쪽과 서로 막히므로, 잠금 있는 쪽은 ``True`` 로 짧게 멈춘다.
    """
    start = threading.Barrier(len(CONFIRMERS))
    read_done = threading.Barrier(len(CONFIRMERS))
    outcomes: dict = {}

    def pause():
        if hold_open:
            time.sleep(0.05)       # 잠금을 쥔 채 머무는 구간
        else:
            read_done.wait(timeout=10)    # 셋이 모두 읽은 뒤에야 쓴다

    def worker(name):
        conn = co.connect(db_path)
        try:
            start.wait(timeout=10)
            outcomes[name] = confirm(conn, session_id, name, pause)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, args=(name,)) for name in CONFIRMERS]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return outcomes


def test_without_a_lock_three_confirmers_grant_three_times(db_path):
    """고치기 전. 세 확정자가 같은 pending 을 보고 각자 다른 키로 적립한다."""
    sid = new_session(db_path)

    outcomes = run_confirmers(db_path, sid, co.confirm_without_lock, hold_open=False)

    assert list(outcomes.values()) == [True, True, True]
    assert snapshot(db_path, sid) == (STATUS_PAID, 3, 3 * UNITS)


def test_with_the_lock_exactly_one_confirmer_grants(db_path):
    sid = new_session(db_path)

    outcomes = run_confirmers(db_path, sid, co.confirm_with_lock, hold_open=True)

    assert sorted(outcomes.values()) == [False, False, True]
    assert snapshot(db_path, sid) == (STATUS_PAID, 1, UNITS)


def test_the_lock_holds_on_every_round(db_path):
    for round_number in range(10):
        sid = new_session(db_path, f"round-{round_number}")
        outcomes = run_confirmers(db_path, sid, co.confirm_with_lock, hold_open=True)
        assert list(outcomes.values()).count(True) == 1, round_number
    conn = co.connect(db_path)
    try:
        assert co.wallet_total(conn, WALLET) == 10 * UNITS
    finally:
        conn.close()


def test_idempotency_keys_differ_per_confirmer_so_the_ledger_cannot_stop_the_overlap(db_path):
    sid = new_session(db_path)
    conn = co.connect(db_path)
    try:
        with co.transaction(conn):
            wallet_id, units, _status = co.lock_payment_session(conn, sid)
            assert co.grant(conn, sid, "notification", wallet_id, units) is True
            assert co.grant(conn, sid, "callback", wallet_id, units) is True    # 유니크 제약이 막지 못한다
            assert co.grant(conn, sid, "callback", wallet_id, units) is False   # 같은 확정자의 재전송만 막힌다
    finally:
        conn.close()
    assert snapshot(db_path, sid)[1] == 2


def test_the_same_confirmer_redelivering_is_stopped_by_its_own_key(db_path):
    sid = new_session(db_path)
    conn = co.connect(db_path)
    try:
        assert co.confirm_with_lock(conn, sid, "notification") is True
        assert co.confirm_with_lock(conn, sid, "notification") is False
    finally:
        conn.close()
    assert snapshot(db_path, sid) == (STATUS_PAID, 1, UNITS)


def test_a_later_confirmer_sees_the_paid_session_and_skips(db_path):
    sid = new_session(db_path)
    conn = co.connect(db_path)
    try:
        assert co.confirm_with_lock(conn, sid, "reconciler") is True
        assert co.confirm_with_lock(conn, sid, "notification") is False
        assert co.confirm_with_lock(conn, sid, "callback") is False
    finally:
        conn.close()
    assert snapshot(db_path, sid) == (STATUS_PAID, 1, UNITS)


def test_unknown_session_is_not_granted(db_path):
    conn = co.connect(db_path)
    try:
        assert co.confirm_with_lock(conn, "missing", "notification") is False
        assert co.confirm_without_lock(conn, "missing", "notification") is False
        assert co.wallet_total(conn, WALLET) == 0
    finally:
        conn.close()


def test_reading_the_session_outside_a_transaction_is_refused(db_path):
    sid = new_session(db_path)
    conn = co.connect(db_path)
    try:
        with pytest.raises(RuntimeError):
            co.lock_payment_session(conn, sid)
    finally:
        conn.close()


def test_a_late_payment_event_after_pay_and_refund_does_not_regrant(db_path):
    sid = new_session(db_path)
    conn = co.connect(db_path)
    try:
        assert co.confirm_with_lock(conn, sid, "reconciler") is True
        assert co.refund(conn, sid) is True
        assert co.confirm_with_lock(conn, sid, "notification") is False   # 지연된 결제 알림
    finally:
        conn.close()
    assert snapshot(db_path, sid) == (STATUS_REFUNDED, 1, 0)


def test_a_refund_that_arrives_first_is_offset_by_the_late_payment(db_path):
    sid = new_session(db_path)
    conn = co.connect(db_path)
    try:
        assert co.refund(conn, sid) is True                              # 원 적립 없이 환불이 먼저
        assert co.wallet_total(conn, WALLET) == -UNITS
        assert co.confirm_with_lock(conn, sid, "notification") is True   # 늦은 결제가 상쇄한다
        assert co.confirm_with_lock(conn, sid, "callback") is False      # 그다음 중복은 막힌다
    finally:
        conn.close()
    assert snapshot(db_path, sid) == (STATUS_REFUNDED, 1, 0)


def test_refund_is_idempotent(db_path):
    sid = new_session(db_path)
    conn = co.connect(db_path)
    try:
        co.confirm_with_lock(conn, sid, "callback")
        assert co.refund(conn, sid) is True
        assert co.refund(conn, sid) is False
    finally:
        conn.close()
    assert snapshot(db_path, sid) == (STATUS_REFUNDED, 1, 0)


def test_a_pending_session_is_not_fulfilled(db_path):
    sid = new_session(db_path)
    conn = co.connect(db_path)
    try:
        assert co.already_fulfilled(conn, sid) is False
    finally:
        conn.close()
    assert snapshot(db_path, sid)[0] == STATUS_PENDING
