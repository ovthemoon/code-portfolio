"""PC가 꺼져 있던 동안 지난 반복 업무 회차를 찾아내는 계획기.

메모리 스케줄러는 기동 이전의 슬롯을 발화하지 않는다. 종전 캐치업은 자는 동안 지난 슬롯을
기록도 없이 버렸다. 여기서는 (마지막 생존 시각, 지금] 창의 슬롯을 실행하거나, "놓침"으로
기록하게 하는 계획을 만든다.

1. 데몬이 주기적으로 "살아 있음" 시각(``last_alive``)을 파일에 남긴다.
2. 부팅하면 그 시각을 읽은 뒤에 새로 쓴다. 쓰기를 먼저 하면 기준선이 지금으로 덮인다.
3. 창 안의 슬롯을 세어, 허용 시간 안이면 실행하고 지났으면 기록한다.
4. 깨어난 직후 한꺼번에 몰리지 않도록 실행 개수에 상한을 둔다. 넘는 것은 기록으로 돌린다.

계획은 순수 함수다. 실행과 기록은 호출자가 한다.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Iterable, Optional, Protocol

logger = logging.getLogger("missed_schedule")

MAX_LOOKBACK = timedelta(days=7)
WAKE_BURST_CAP_DEFAULT = 5
SLOT_WALK_CAP = 2000

REASON_MISSED = "missed_asleep"
REASON_BURST = "missed_asleep_burst_cap"
ACTION_EXECUTE = "execute"
ACTION_RECORD = "record"

DELIVERY_AT_MOST_ONCE = "at_most_once"      # 허용 시간 안이면 따라잡고, 지났으면 기록만
DELIVERY_AT_LEAST_ONCE = "at_least_once"    # 오래됐어도 가장 최근 회차를 1회 실행

# 주기에 비례하는 허용 시간: clamp(주기 / 2, 최소, 최대). 주기를 모르면 기본값.
DEFAULT_MISFIRE_GRACE_SECONDS = 60
MIN_MISFIRE_GRACE_SECONDS = 120
MAX_MISFIRE_GRACE_SECONDS = 7200
_FREQUENCY_PERIOD_SECONDS = {
    "hourly": 3_600,
    "daily": 86_400,
    "weekly": 604_800,
    "monthly": 2_592_000,
}

# 슬롯 역탐색 창 사다리. 작은 창부터 넓혀 탐색 횟수를 유계로 둔다
# (분 단위 업무도 첫 창 3시간에서 180번 안쪽). 마지막 창은 연 1회 업무까지 덮는다.
_SLOT_LOOKBACK_SECONDS = (3 * 3_600, 26 * 3_600, 8 * 86_400, 32 * 86_400, 366 * 86_400)


class Schedule(Protocol):
    def next_after(self, moment: datetime) -> Optional[datetime]:
        """``moment`` 보다 엄밀히 나중인 다음 슬롯. 없으면 None."""


@dataclass(frozen=True)
class DailySchedule:
    hour: int
    minute: int = 0
    tz: tzinfo = timezone.utc

    def next_after(self, moment: datetime) -> Optional[datetime]:
        local = moment.astimezone(self.tz)
        candidate = local.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        if candidate <= local:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)


@dataclass(frozen=True)
class IntervalSchedule:
    every: timedelta
    anchor: datetime

    def next_after(self, moment: datetime) -> Optional[datetime]:
        if moment < self.anchor:
            return self.anchor
        steps = (moment - self.anchor) // self.every + 1
        return self.anchor + steps * self.every


@dataclass(frozen=True)
class CronJob:
    cron_id: str
    schedule: Optional[Schedule] = None
    frequency: str = "daily"
    delivery: str = DELIVERY_AT_MOST_ONCE
    enabled: bool = True
    awaiting_setup: bool = False
    event_trigger: str = ""            # 이벤트로 도는 업무는 시각으로 깨우지 않는다
    run_once_at: str = ""              # 한 번만 도는 업무의 ISO 시각
    last_fired_slot: str = ""          # 마지막으로 발화한 슬롯의 UTC ISO 키
    last_result: str = ""


@dataclass(frozen=True)
class MissedSlot:
    cron_id: str
    slot: datetime          # aware UTC. 가장 최근에 지난 슬롯
    count: int              # 창 안 슬롯 수(SLOT_WALK_CAP 에서 멈춤)
    action: str             # ACTION_EXECUTE | ACTION_RECORD
    reason: str = ""


def slot_key(slot: datetime) -> str:
    """같은 물리적 순간이면 같은 키. 로컬 오프셋이 흔들려도 멱등 비교가 깨지지 않는다."""
    return slot.astimezone(timezone.utc).isoformat()


def misfire_grace_seconds(job: CronJob) -> int:
    period = _FREQUENCY_PERIOD_SECONDS.get((job.frequency or "").strip().lower(), 0)
    if period <= 0:
        return DEFAULT_MISFIRE_GRACE_SECONDS
    return max(MIN_MISFIRE_GRACE_SECONDS, min(MAX_MISFIRE_GRACE_SECONDS, period // 2))


def wakes_machine(job: CronJob) -> bool:
    """이 업무의 발화가 잠든 기계를 깨울 자격이 있는가."""
    return job.enabled and not job.awaiting_setup and not job.event_trigger


def _alive_path(base_dir: str) -> str:
    return os.path.join(base_dir, "state", "last_alive.json")


def _atomic_write_json(path: str, payload: dict) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_last_alive(base_dir: str, now_epoch: Optional[float] = None) -> None:
    ts = time.time() if now_epoch is None else float(now_epoch)
    try:
        _atomic_write_json(_alive_path(base_dir), {"ts": ts, "pid": os.getpid()})
    except OSError:
        logger.warning("[last_alive] write failed (ignored)", exc_info=True)  # 마커 실패가 데몬을 죽이면 안 된다


def read_last_alive(base_dir: str) -> Optional[datetime]:
    """깨진 마커(JSON 손상, 비정상 ts)는 None. 부팅 경로를 절대 죽이지 않는다."""
    try:
        with open(_alive_path(base_dir), "r", encoding="utf-8") as handle:
            ts = float((json.load(handle) or {}).get("ts"))
        return datetime.fromtimestamp(ts, timezone.utc)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        logger.warning("[last_alive] unreadable marker, treating as no baseline", exc_info=True)
        return None


def _parse_iso_utc(value: str) -> Optional[datetime]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()   # 시각대가 없으면 로컬로 본다
    return parsed.astimezone(timezone.utc)


def _slot_walk_latest(schedule: Schedule, after: datetime, until: datetime) -> Optional[datetime]:
    """(after, until] 구간의 슬롯 중 가장 늦은 것."""
    latest: Optional[datetime] = None
    prev = after
    for _ in range(SLOT_WALK_CAP):
        nxt = schedule.next_after(prev)
        if nxt is None or nxt > until:
            break
        latest, prev = nxt, nxt
    return latest


def _latest_elapsed_slot(schedule: Schedule, now: datetime) -> Optional[datetime]:
    for lookback in _SLOT_LOOKBACK_SECONDS:
        slot = _slot_walk_latest(schedule, now - timedelta(seconds=lookback), now)
        if slot is not None:
            return slot
    return None


def _count_slots(schedule: Schedule, after: datetime, until: datetime) -> int:
    n, prev = 0, after
    while n < SLOT_WALK_CAP:
        nxt = schedule.next_after(prev)
        if nxt is None or nxt > until:
            break
        n, prev = n + 1, nxt
    return n


def _plan_one(job: CronJob, floor: datetime, now: datetime) -> Optional[MissedSlot]:
    if not wakes_machine(job):
        return None
    if job.run_once_at:
        if job.last_result == "queued_busy":
            return None
        at = _parse_iso_utc(job.run_once_at)
        if at is None or not (floor < at <= now):
            return None
        return MissedSlot(job.cron_id, at, 1, ACTION_RECORD, REASON_MISSED)   # 한 번짜리는 기록만
    if job.schedule is None:
        return None
    fired = _parse_iso_utc(job.last_fired_slot)
    baseline = max(floor, fired) if fired is not None else floor
    try:
        latest = _latest_elapsed_slot(job.schedule, now)
    except Exception:  # noqa: BLE001 - 깨진 스케줄 하나가 부팅 전체를 막지 않게
        return None
    if latest is None:
        return None
    latest = latest.astimezone(timezone.utc)
    if latest <= baseline:
        return None
    count = _count_slots(job.schedule, baseline, latest)
    if (now - latest).total_seconds() <= misfire_grace_seconds(job) \
            or job.delivery == DELIVERY_AT_LEAST_ONCE:
        return MissedSlot(job.cron_id, latest, count, ACTION_EXECUTE)
    return MissedSlot(job.cron_id, latest, count, ACTION_RECORD, REASON_MISSED)


def plan_missed(jobs: Iterable[CronJob], *, since: datetime, now: datetime,
                burst_cap: int = WAKE_BURST_CAP_DEFAULT) -> list[MissedSlot]:
    """(since, now] 창의 놓친 회차 계획. 기록 항목이 앞, 실행 항목이 뒤(오래된 슬롯 우선)."""
    floor = max(since, now - MAX_LOOKBACK)
    planned = [m for m in (_plan_one(j, floor, now) for j in jobs) if m is not None]
    record = [m for m in planned if m.action == ACTION_RECORD]
    execute = sorted((m for m in planned if m.action == ACTION_EXECUTE),
                     key=lambda m: (m.slot, m.cron_id))
    cap = max(1, int(burst_cap))
    overflow = [replace(m, action=ACTION_RECORD, reason=REASON_BURST) for m in execute[cap:]]
    return [*record, *overflow, *execute[:cap]]


def plan_at_boot(jobs: Iterable[CronJob], *, base_dir: str, now: datetime,
                 burst_cap: int = WAKE_BURST_CAP_DEFAULT) -> list[MissedSlot]:
    """부팅 흐름: 마커를 읽고, 계획을 세우고, 그다음에 마커를 새로 쓴다.

    마커가 없으면 기준선이 없으므로 계획은 비어 있다(첫 부팅).
    """
    since = read_last_alive(base_dir)
    plan = [] if since is None else plan_missed(jobs, since=since, now=now, burst_cap=burst_cap)
    write_last_alive(base_dir, now.timestamp())
    return plan
