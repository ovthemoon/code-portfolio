"""호출 무게: "이 호출 하나가 사람을 부를 만큼 무거운가"를 셀 수 있는 사실로 잰다.

이전 판단의 단위는 도구 종류였다. 그래서 '알아서' 한 번이 받는 사람과 금액에 상관없이
그 종류 전체를 풀었다. 여기서는 호출 하나의 네 축을 잰다. 되돌릴 수 있나, 누가 받나,
얼마인가, 해 본 일인가. 모델에게 묻지 않는다.

- 가장 무거운 축 하나가 등급을 정한다. 더하지 않는다.
- '하고 알림'은 되돌릴 수 있는 일에만 준다. 이미 보낸 메일은 알림을 받아도 할 수 있는 일이 없다.
- 이 모듈은 순수하다. I/O 도, 시계도(``now`` 는 호출자가 준다), 저장소도 없다. 주소록과
  실적 조회는 호출자가 함수로 넣는다. 그래서 경우의 수를 표로 테스트할 수 있다.

``risk`` 와 ``gate_reason`` 은 이 모듈 바깥의 위험 분류기가 준다. 이 모듈은 그 분류를
바꾸지 않고, 무게로 "신뢰로 확인을 생략해도 되는가"와 "카드에 붙일 이유"만 정한다.

아래 상수와 키 목록은 예시값이다. 운영에서 쓰는 값과 다르다.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any, Callable, Final, Iterable, Mapping, Optional


class Weight(IntEnum):
    LIGHT = 0
    MID = 1
    HEAVY = 2


class Tier(str, Enum):
    NONE = "none"        # 조용히 실행
    NOTIFY = "notify"    # 실행하고 알림
    ASK = "ask"          # 사람에게 확인


# 예시값. 보안 임계값이라 실제 값은 싣지 않았다.
MONEY_AUTO_LIMIT: Final[float] = 100     # 이 금액을 넘으면 항상 묻는다
SPOT_CHECK_EVERY: Final[int] = 10        # 자율 실행 N번에 1번은 다시 묻는다(결정론)
TRUST_TTL_DAYS: Final[int] = 30          # 마지막 승인이 이보다 오래되면 "해 본 일"이 아니다
_DAY_SECONDS: Final[int] = 86400

# 예시 목록. 권한 칸(kind)의 이름과 분류.
IRREVERSIBLE_KINDS: Final[frozenset] = frozenset({"external_send", "publish", "purchase", "record_delete"})
SEND_KINDS: Final[frozenset] = frozenset({"external_send"})
SPEND_KINDS: Final[frozenset] = frozenset({"purchase"})

# 위험 분류기가 내는 값의 어휘(예시).
IRREVERSIBLE_RISKS: Final[frozenset] = frozenset(
    {"send_external", "irreversible", "bulk_irreversible", "sensitive_path"}
)
# "신호는 없지만 모르니 막는다"로 내려오는 이유. 이때의 risk="destructive"는 증거가 아니라 기본값이다.
CATCHALL_REASONS: Final[frozenset] = frozenset({"unverified", "unclassified", "write"})

# 받는 사람을 가리키는 인자 이름(예시). 키는 _norm_key 형태(소문자, 구분자 제거).
RECIPIENT_KEYS: Final[frozenset] = frozenset({
    "to", "recipient", "recipients", "email", "emails", "cc", "bcc",
    "attendees", "invitees", "guests",
})
AMOUNT_KEYS: Final[frozenset] = frozenset({"amount", "budget", "dailybudget", "price", "total"})
# 받는 사람은 아니지만 호출이 닿는 대상 수에만 세는 인자.
COUNT_ONLY_KEYS: Final[frozenset] = frozenset({"ids"})

# 중첩 객체(예: {"event": {"attendees": [...]}})도 이 깊이까지 들어가 받는 사람을 찾는다.
_RECIPIENT_NEST: Final[int] = 2
_MAX_NEST: Final[int] = 2

_ADDRESS_SPLIT = re.compile(r"[,;\n]")
_ANGLE_ADDRESS = re.compile(r"<([^<>]*)>")
# 금액 문자열: 통화 기호나 단위, 앞뒤 공백, 천 단위 쉼표만 허용한다. 나머지가 숫자 하나가 아니면 읽지 않는다.
_CURRENCY_UNITS: Final[tuple] = ("krw", "usd", "eur", "jpy", "won", "원", "$", "₩", "€", "£", "¥")
_UNIT = "|".join(re.escape(u) for u in sorted(_CURRENCY_UNITS, key=len, reverse=True))
_AMOUNT_TEXT = re.compile(
    rf"(?:(?:{_UNIT})\s*)?((?:[0-9]{{1,3}}(?:,[0-9]{{3}})+|[0-9]+)(?:\.[0-9]+)?)(?:\s*(?:{_UNIT}))?",
    re.IGNORECASE | re.ASCII,
)
_DICT_ADDRESS_KEYS: Final[tuple] = ("email", "address", "value", "id", "name")


@dataclass(frozen=True)
class Reason:
    """카드에 붙는 이유 한 조각. ``code`` 는 문구를 찾는 키이고 나머지는 자리표시 값이다."""
    code: str
    count: int = 0
    amount: str = ""


@dataclass(frozen=True)
class CallWeight:
    reversibility: Weight
    audience: Weight
    amount: Weight
    track: Weight
    reasons: tuple = ()
    recipients: tuple = ()          # 정규화된 받는 사람
    amount_value: Optional[float] = None
    spot_check: bool = False        # 자율로 여러 번 돈 신뢰 항목이 이번에 다시 물을 차례인가

    @property
    def is_heavy(self) -> bool:
        return Weight.HEAVY in (self.reversibility, self.audience, self.amount, self.track)

    @property
    def is_mid(self) -> bool:
        return Weight.MID in (self.audience, self.amount)


@dataclass(frozen=True)
class AmountRead:
    present: bool
    readable: bool
    value: Optional[float]     # 읽은 값 중 가장 큰 것(여러 필드면 가장 무거운 쪽으로 판정)


def _norm_key(key: Any) -> str:
    return str(key).lower().replace("_", "").replace("-", "")


def normalize_address(value: Any) -> str:
    """주소 비교용 정규화. 앞뒤 공백과 따옴표를 지우고, ``이름 <a@b.c>`` 는 안쪽만, 소문자로."""
    text = str(value if value is not None else "").strip()
    angle = _ANGLE_ADDRESS.search(text)
    if angle:
        text = angle.group(1)
    return text.strip().strip("'\"").strip().lower()


def _iter_address_items(value: Any, depth: int = 0) -> Iterable[str]:
    if isinstance(value, str):
        yield from (p for p in _ADDRESS_SPLIT.split(value) if p.strip())
    elif isinstance(value, bool):
        return
    elif isinstance(value, (int, float)):
        yield str(value)
    elif isinstance(value, Mapping):
        for key in _DICT_ADDRESS_KEYS:
            got = value.get(key)
            if isinstance(got, (str, int)) and not isinstance(got, bool) and str(got).strip():
                yield str(got)
                return
    elif isinstance(value, (list, tuple, set, frozenset)) and depth < _MAX_NEST:
        for item in value:
            yield from _iter_address_items(item, depth + 1)


def extract_recipients(args: Any) -> tuple:
    """인자에서 받는 사람(정규화, 중복 제거, 등장 순서)을 뽑는다. 받는 사람이 없으면 빈 튜플."""
    if not isinstance(args, Mapping):
        return ()
    found: dict = {}
    _collect_recipients(args, found, 0)
    return tuple(found)


def _collect_recipients(args: Mapping, found: dict, depth: int) -> None:
    for key, value in args.items():
        if _norm_key(key) in RECIPIENT_KEYS:
            for item in _iter_address_items(value):
                address = normalize_address(item)
                if address:
                    found.setdefault(address, None)
        elif isinstance(value, Mapping) and depth < _RECIPIENT_NEST:
            _collect_recipients(value, found, depth + 1)


def _count_only_targets(args: Any) -> int:
    """받는 사람은 아니지만 호출이 닿는 대상 수. 대량 판정에만 쓴다."""
    if not isinstance(args, Mapping):
        return 0
    n = 0
    for key, value in args.items():
        if _norm_key(key) in COUNT_ONLY_KEYS:
            n = max(n, sum(1 for _ in _iter_address_items(value)))
    return n


def _read_number(value: Any) -> Optional[float]:
    """금액 하나를 읽는다. 읽지 못하면(음수, 비정상 값, 숫자 하나가 아닌 문자열) None. None 은 무겁게 본다."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        match = _AMOUNT_TEXT.fullmatch(value.strip())
        if not match:
            return None
        value = float(match.group(1).replace(",", ""))
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) and value >= 0 else None
    return None


def extract_amount(args: Any) -> AmountRead:
    """금액 필드가 있는지, 전부 읽었는지, 가장 큰 값. 비어 있는 필드(None, "")는 없는 것으로 본다."""
    if not isinstance(args, Mapping):
        return AmountRead(False, True, None)
    values = []
    present = False
    readable = True
    for key, raw in args.items():
        if _norm_key(key) not in AMOUNT_KEYS or raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        present = True
        number = _read_number(raw)
        if number is None:
            readable = False
        else:
            values.append(number)
    return AmountRead(present, readable, max(values) if values else None)


def format_amount(value: float) -> str:
    """표시용. 정수면 천 단위 쉼표, 아니면 소수 둘째 자리까지."""
    return f"{int(value):,}" if float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")


def _entry_int(entry: Mapping, key: str) -> int:
    try:
        return int(entry.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _entry_float(entry: Mapping, key: str) -> float:
    try:
        return float(entry.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def trust_state(entry: Optional[Mapping], now: float) -> str:
    """이 (칸, 대상)의 실적 -> ``ok`` | ``none``(승인받은 적 없음, 거절로 끊김) | ``expired``(기한 넘음).

    신뢰는 마지막으로 사람이 답한 것이 그대로 승인이고(streak >= 1) 마지막 승인이나 자율
    실행이 기한 안일 때만 성립한다. 거절과 수정 승인은 streak 를 0 으로 만들어 신뢰를 끊는다.
    """
    if not isinstance(entry, Mapping) or _entry_int(entry, "approved") < 1 or _entry_int(entry, "streak") < 1:
        return "none"
    if now - _entry_float(entry, "lastAt") > TRUST_TTL_DAYS * _DAY_SECONDS:
        return "expired"
    return "ok"


def is_spot_check(entry: Optional[Mapping]) -> bool:
    """자율 실행이 N-1, 2N-1, ... 번 쌓인 항목이면 다음(N번째)은 다시 묻는다."""
    return isinstance(entry, Mapping) and _entry_int(entry, "autoUses") % SPOT_CHECK_EVERY == SPOT_CHECK_EVERY - 1


def _never_known(_address: str) -> bool:
    return False


def _no_trust(_target: str) -> Optional[Mapping]:
    return None


def _reversibility(kind: str, risk: str, gate_reason: str) -> tuple:
    heavy = (kind in IRREVERSIBLE_KINDS or risk in IRREVERSIBLE_RISKS
             or (risk == "destructive" and gate_reason not in CATCHALL_REASONS))
    if not heavy:
        return Weight.LIGHT, ()
    sends = kind in SEND_KINDS or risk == "send_external"
    return Weight.HEAVY, (Reason("irreversible_send" if sends else "irreversible"),)


# 일정 초대는 '보내는' 일이 아니라 함께하는 사람이다. 같은 축을 참석자 말로 적는다.
_PEOPLE_WORDS: Final[dict] = {"calendar_write": ("attendees", "new_attendee", "new_attendees")}
_DEFAULT_PEOPLE_WORDS: Final[tuple] = ("recipients", "new_recipient", "new_recipients")
NEW_PERSON_CODES: Final[frozenset] = frozenset({"new_recipient", "new_recipients", "new_attendee", "new_attendees"})


def _audience(recipients: tuple, count: int, bulk_threshold: int, is_known: Callable[[str], bool],
              kind: str = "") -> tuple:
    people, new_one, new_many = _PEOPLE_WORDS.get(kind, _DEFAULT_PEOPLE_WORDS)
    unknown = sum(1 for r in recipients if not is_known(r))
    bulk = count >= max(1, int(bulk_threshold))
    reasons: list = []
    if bulk or (recipients and not unknown):
        reasons.append(Reason(people, count=count))
    if unknown:
        reasons.append(Reason(new_one if unknown == 1 else new_many, count=unknown))
    if bulk or unknown:
        return Weight.HEAVY, tuple(reasons)
    return (Weight.MID if recipients else Weight.LIGHT), tuple(reasons)


def _amount(kind: str, read: AmountRead) -> tuple:
    if not read.present and kind not in SPEND_KINDS:
        return Weight.LIGHT, ()
    if not read.present or not read.readable:
        return Weight.HEAVY, (Reason("amount_unknown"),)
    shown = Reason("amount", amount=format_amount(read.value or 0))
    return (Weight.HEAVY if (read.value or 0) > MONEY_AUTO_LIMIT else Weight.MID), (shown,)


def _track(kind: str, targets: tuple, trust: Callable[[str], Optional[Mapping]], now: float,
           suppress_reason: bool) -> tuple:
    """(가중치, 이유, 불시 점검 차례). 칸이 없는 도구는 실적을 셀 수 없으니 재지 않는다."""
    if not kind:
        return Weight.LIGHT, (), False
    entries = [trust(t) for t in targets]
    states = [trust_state(e, now) for e in entries]
    if all(s == "ok" for s in states):
        return Weight.LIGHT, (), any(is_spot_check(e) for e in entries)
    if suppress_reason:   # 받는 사람이 처음이라는 이유가 이미 같은 말을 한다
        return Weight.HEAVY, (), False
    return Weight.HEAVY, (Reason("first_time" if "none" in states else "trust_expired"),), False


def weigh(*, kind: str, args: Any, risk: str = "", gate_reason: str = "", bulk_threshold: int = 10,
          is_known: Callable[[str], bool] = _never_known,
          trust: Callable[[str], Optional[Mapping]] = _no_trust, now: float) -> CallWeight:
    """호출 하나의 무게. ``kind`` 는 도구가 속한 권한 칸(없으면 ""), ``risk`` 와 ``gate_reason`` 은 위험 분류기의 판정.

    ``is_known(주소)`` 는 사용자가 승인한 주소록에 있는지, ``trust(대상)`` 은 이 (칸, 대상)의 실적
    항목이다(대상은 받는 사람 각각, 없으면 ""). 예외를 던지지 않는다. 잡는 것은 호출자의 몫이다.
    """
    recipients = extract_recipients(args)
    count = max(len(recipients), _count_only_targets(args))
    audience, audience_reasons = _audience(recipients, count, bulk_threshold, is_known, kind)
    reversibility, reversibility_reasons = _reversibility(kind, risk, gate_reason)
    read = extract_amount(args)
    amount, amount_reasons = _amount(kind, read)
    track, track_reasons, spot = _track(
        kind, recipients or ("",), trust, now,
        suppress_reason=any(r.code in NEW_PERSON_CODES for r in audience_reasons))
    return CallWeight(
        reversibility=reversibility, audience=audience, amount=amount, track=track,
        reasons=audience_reasons + reversibility_reasons + amount_reasons + track_reasons,
        recipients=recipients, amount_value=read.value, spot_check=spot,
    )


def decide(weight: CallWeight, *, allowed: bool, spot_check: bool) -> Tier:
    """무게 + 사용자의 '알아서' 허락 -> 등급. 무거운 축이 하나라도 있거나 허락이 없거나 불시 점검 차례면 ASK."""
    if weight.is_heavy or not allowed or spot_check:
        return Tier.ASK
    return Tier.NOTIFY if weight.is_mid else Tier.NONE
