"""자는 동안 지난 회차: 실행하거나 기록한다. 여러 슬롯, 몰아치기 상한, 마커 읽기와 쓰기 순서."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import missed_schedule as ms
from missed_schedule import (
    ACTION_EXECUTE,
    ACTION_RECORD,
    DELIVERY_AT_LEAST_ONCE,
    REASON_BURST,
    REASON_MISSED,
    CronJob,
    DailySchedule,
    IntervalSchedule,
    MissedSlot,
    plan_missed,
)

UTC = timezone.utc
KST = timezone(timedelta(hours=9))

SINCE = datetime(2026, 9, 30, 23, 0, tzinfo=UTC)         # 10-01 08:00 KST, 마지막 생존
SLOT_OCT2 = datetime(2026, 10, 2, 0, 0, tzinfo=UTC)      # 10-02 09:00 KST
NOW_LATE = datetime(2026, 10, 2, 3, 0, tzinfo=UTC)       # 12:00 KST, 최근 슬롯은 3시간 전
NOW_ON_TIME = datetime(2026, 10, 2, 0, 1, tzinfo=UTC)    # 09:01 KST, 1분 지남


def daily(cron_id="d1", hour=9, **kw) -> CronJob:
    return CronJob(cron_id=cron_id, schedule=DailySchedule(hour, tz=KST), frequency="daily", **kw)


def test_daily_schedule_returns_the_next_slot_strictly_after():
    schedule = DailySchedule(9, tz=KST)
    assert schedule.next_after(datetime(2026, 10, 1, 23, 59, tzinfo=UTC)) == SLOT_OCT2
    assert schedule.next_after(SLOT_OCT2) == SLOT_OCT2 + timedelta(days=1)


def test_interval_schedule_steps_from_its_anchor():
    anchor = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
    schedule = IntervalSchedule(timedelta(minutes=30), anchor)
    assert schedule.next_after(anchor - timedelta(hours=1)) == anchor
    assert schedule.next_after(anchor) == anchor + timedelta(minutes=30)
    assert schedule.next_after(anchor + timedelta(minutes=31)) == anchor + timedelta(minutes=60)


@pytest.mark.parametrize("frequency,expected", [
    ("daily", 7200), ("weekly", 7200), ("hourly", 1800), ("", 60), ("event", 60),
])
def test_misfire_grace_scales_with_the_period_and_is_clamped(frequency, expected):
    assert ms.misfire_grace_seconds(CronJob("x", frequency=frequency)) == expected


def test_two_slots_missed_across_sleep_become_one_record_with_a_count():
    plan = plan_missed([daily()], since=SINCE, now=NOW_LATE)   # 최근 슬롯이 허용 시간(2시간)을 넘었다
    assert plan == [MissedSlot("d1", SLOT_OCT2, 2, ACTION_RECORD, REASON_MISSED)]


def test_slot_within_grace_is_executed_even_when_at_most_once():
    plan = plan_missed([daily()], since=SINCE, now=NOW_ON_TIME)
    assert [(m.action, m.slot, m.count) for m in plan] == [(ACTION_EXECUTE, SLOT_OCT2, 2)]


def test_at_least_once_executes_the_latest_even_when_old():
    plan = plan_missed([daily(delivery=DELIVERY_AT_LEAST_ONCE)], since=SINCE, now=NOW_LATE)
    assert [(m.action, m.slot) for m in plan] == [(ACTION_EXECUTE, SLOT_OCT2)]


def test_already_fired_slot_is_not_reported_missed():
    """마커가 최대 한 주기 낡아 이미 발화한 슬롯이 창에 들어와도 중복 기록하지 않는다."""
    job = daily(last_fired_slot=ms.slot_key(SLOT_OCT2))
    assert plan_missed([job], since=SINCE, now=NOW_LATE) == []


def test_no_slot_in_window_means_an_empty_plan():
    since = datetime(2026, 10, 2, 0, 5, tzinfo=UTC)
    now = datetime(2026, 10, 2, 1, 0, tzinfo=UTC)
    assert plan_missed([daily()], since=since, now=now) == []


def test_ineligible_jobs_are_ignored():
    jobs = [
        daily("off", enabled=False),
        daily("setup", awaiting_setup=True),
        CronJob("evt", schedule=IntervalSchedule(timedelta(minutes=5), SINCE), event_trigger="new-mail"),
    ]
    assert plan_missed(jobs, since=SINCE, now=NOW_LATE) == []


def test_one_shot_in_window_is_recorded_not_executed():
    at = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    shot = CronJob("s1", run_once_at=at.isoformat())
    before_window = CronJob("s0", run_once_at=(SINCE - timedelta(hours=1)).isoformat())
    busy = CronJob("s2", run_once_at=at.isoformat(), last_result="queued_busy")
    broken = CronJob("s3", run_once_at="not a time")
    plan = plan_missed([shot, before_window, busy, broken], since=SINCE, now=NOW_LATE)
    assert plan == [MissedSlot("s1", at, 1, ACTION_RECORD, REASON_MISSED)]


def test_burst_cap_keeps_the_oldest_executions_and_records_the_rest():
    jobs = [daily(f"j{h}", hour=h, delivery=DELIVERY_AT_LEAST_ONCE) for h in range(1, 9)]  # 8개
    plan = plan_missed(jobs, since=SINCE, now=NOW_LATE, burst_cap=5)
    executed = [m for m in plan if m.action == ACTION_EXECUTE]
    burst = [m for m in plan if m.reason == REASON_BURST]
    assert len(executed) == 5 and len(burst) == 3
    assert all(m.action == ACTION_RECORD for m in burst)
    assert plan.index(burst[-1]) < plan.index(executed[0])     # 기록이 실행보다 앞
    assert max(m.slot for m in executed) <= min(m.slot for m in burst)   # 살아남은 실행은 가장 이른 슬롯들


def test_burst_cap_has_a_floor_of_one():
    jobs = [daily(f"j{h}", hour=h, delivery=DELIVERY_AT_LEAST_ONCE) for h in (1, 2)]
    plan = plan_missed(jobs, since=SINCE, now=NOW_LATE, burst_cap=0)
    assert sum(m.action == ACTION_EXECUTE for m in plan) == 1


def test_lookback_is_limited_to_seven_days():
    now = datetime(2026, 10, 20, 3, 0, tzinfo=UTC)
    plan = plan_missed([daily()], since=now - timedelta(days=30), now=now)
    assert plan[0].count <= 8   # 하루 한 번 업무의 7일 창


def test_minute_job_walk_is_capped_and_bounded():
    class Counting(IntervalSchedule):
        calls = 0

        def next_after(self, moment):
            type(self).calls += 1
            return super().next_after(moment)

    now = datetime(2026, 10, 10, 3, 0, 30, tzinfo=UTC)
    job = CronJob("m", schedule=Counting(timedelta(minutes=1), now - timedelta(days=60)), frequency="hourly")
    plan = plan_missed([job], since=now - timedelta(days=30), now=now)
    assert plan[0].count == ms.SLOT_WALK_CAP          # 7일 창이라도 상한에서 멈춘다
    assert Counting.calls <= 2 * ms.SLOT_WALK_CAP + 200   # 최근 슬롯 찾기는 작은 창부터라 짧게 끝난다


def test_a_broken_schedule_is_skipped_not_fatal():
    class Broken:
        def next_after(self, moment):
            raise RuntimeError("bad expression")

    plan = plan_missed([CronJob("bad", schedule=Broken()), daily()], since=SINCE, now=NOW_LATE)
    assert [m.cron_id for m in plan] == ["d1"]


def test_last_alive_roundtrip(tmp_path):
    base = str(tmp_path)
    assert ms.read_last_alive(base) is None
    ms.write_last_alive(base, 1_790_000_000.0)
    assert ms.read_last_alive(base) == datetime.fromtimestamp(1_790_000_000.0, UTC)


def test_corrupt_marker_reads_none(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "last_alive.json").write_text("{oops", encoding="utf-8")
    assert ms.read_last_alive(str(tmp_path)) is None


@pytest.mark.parametrize("ts", [1e30, float("nan"), float("inf"), -1e30])
def test_out_of_range_timestamp_reads_none(tmp_path, ts):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "last_alive.json").write_text(json.dumps({"ts": ts}), encoding="utf-8")
    assert ms.read_last_alive(str(tmp_path)) is None


def test_marker_write_failure_does_not_raise(tmp_path):
    blocker = tmp_path / "state"
    blocker.write_text("a file where the directory should be", encoding="utf-8")
    ms.write_last_alive(str(tmp_path), 1_790_000_000.0)    # 예외 없이 지나가야 한다
    assert ms.read_last_alive(str(tmp_path)) is None


def test_marker_write_leaves_no_temp_files(tmp_path):
    ms.write_last_alive(str(tmp_path), 1_790_000_000.0)
    assert [p.name for p in (tmp_path / "state").iterdir()] == ["last_alive.json"]


def test_boot_plans_from_the_old_marker_then_rewrites_it(tmp_path):
    base = str(tmp_path)
    ms.write_last_alive(base, SINCE.timestamp())

    first = ms.plan_at_boot([daily()], base_dir=base, now=NOW_LATE)
    second = ms.plan_at_boot([daily()], base_dir=base, now=NOW_LATE + timedelta(minutes=1))

    assert first == [MissedSlot("d1", SLOT_OCT2, 2, ACTION_RECORD, REASON_MISSED)]
    assert second == []     # 마커가 갱신됐으므로 같은 회차를 두 번 계획하지 않는다
    assert ms.read_last_alive(base) == NOW_LATE + timedelta(minutes=1)


def test_first_boot_without_a_marker_has_no_baseline_and_writes_one(tmp_path):
    base = str(tmp_path)
    assert ms.plan_at_boot([daily()], base_dir=base, now=NOW_LATE) == []
    assert ms.read_last_alive(base) == NOW_LATE
