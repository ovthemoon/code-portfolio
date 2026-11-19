"""호출 무게: weigh 와 decide 의 경우의 수 표. 순수 함수라 저장소 없이 돈다.

상수는 예시값이므로 테스트는 값을 박지 않고 모듈의 상수를 기준으로 경계를 잡는다.
"""

from __future__ import annotations

import pytest

import call_weight as cw
from call_weight import Tier, Weight

NOW = 1_800_000_000.0
DAY = 86400.0
EVERY = cw.SPOT_CHECK_EVERY
ABOVE_LIMIT = int(cw.MONEY_AUTO_LIMIT) + 1


def entry(*, approved=3, streak=3, last_days_ago=1.0, auto_uses=0):
    return {"approved": approved, "rejected": 0, "streak": streak,
            "lastAt": NOW - last_days_ago * DAY, "autoUses": auto_uses}


def weigh(kind="", args=None, risk="", reason="", known=(), trust=None, threshold=10):
    trust = trust or {}
    known = {cw.normalize_address(k) for k in known}
    return cw.weigh(kind=kind, args=args or {}, risk=risk, gate_reason=reason, bulk_threshold=threshold,
                    is_known=lambda a: a in known, trust=lambda t: trust.get(t), now=NOW)


def codes(weight):
    return [r.code for r in weight.reasons]


# 축 1: 되돌릴 수 있나

@pytest.mark.parametrize("risk", ["send_external", "irreversible", "bulk_irreversible", "sensitive_path"])
def test_irreversible_risks_are_heavy(risk):
    assert weigh(risk=risk).reversibility is Weight.HEAVY


@pytest.mark.parametrize("kind", sorted(cw.IRREVERSIBLE_KINDS))
def test_irreversible_kinds_are_heavy_whatever_the_risk(kind):
    assert weigh(kind=kind, risk="write").reversibility is Weight.HEAVY


@pytest.mark.parametrize("kind", ["file_write", "calendar_write", ""])
def test_reversible_kinds_with_a_write_risk_are_light(kind):
    assert weigh(kind=kind, risk="write", reason="write").reversibility is Weight.LIGHT


def test_a_real_destructive_signal_is_heavy_but_the_catch_all_default_is_not():
    # 분류기는 신호가 없어도 모르는 도구에 risk=destructive 를 붙인다. 그건 증거가 아니다.
    assert weigh(risk="destructive", reason="destructive").reversibility is Weight.HEAVY
    assert weigh(risk="destructive", reason="unverified").reversibility is Weight.LIGHT
    assert weigh(risk="destructive", reason="unclassified").reversibility is Weight.LIGHT
    assert weigh(risk="destructive", reason="something_new").reversibility is Weight.HEAVY  # 모르면 막는다


def test_send_wording_only_for_sends():
    assert "irreversible_send" in codes(weigh(kind="external_send"))
    assert "irreversible_send" in codes(weigh(risk="send_external"))
    assert "irreversible" in codes(weigh(kind="publish"))
    assert "irreversible_send" not in codes(weigh(kind="publish"))


# 축 2: 누가 받나

def test_no_recipient_is_light():
    w = weigh(kind="file_write", args={"path": "a.txt"})
    assert w.audience is Weight.LIGHT and w.recipients == ()


def test_all_recipients_known_is_mid():
    w = weigh(args={"attendees": ["a@x.com", "b@x.com"]}, known=["a@x.com", "b@x.com"])
    assert w.audience is Weight.MID
    assert codes(w) == ["recipients"] and w.reasons[0].count == 2


def test_one_unknown_recipient_is_heavy_with_the_singular_reason():
    w = weigh(args={"to": "a@x.com, new@x.com"}, known=["a@x.com"])
    assert w.audience is Weight.HEAVY
    assert codes(w) == ["new_recipient"]


def test_several_unknown_recipients_are_counted():
    w = weigh(args={"to": ["a@x.com", "b@x.com", "c@x.com"]}, known=["a@x.com"])
    assert [(r.code, r.count) for r in w.reasons] == [("new_recipients", 2)]


def test_bulk_is_heavy_even_when_everyone_is_known():
    known = [f"u{i}@x.com" for i in range(3)]
    w = weigh(args={"to": known}, known=known, threshold=3)
    assert w.audience is Weight.HEAVY and codes(w) == ["recipients"] and w.reasons[0].count == 3
    assert weigh(args={"to": known}, known=known, threshold=4).audience is Weight.MID


def test_bulk_and_unknown_are_both_reported():
    w = weigh(args={"to": ["a@x.com", "b@x.com", "c@x.com"]}, known=["a@x.com"], threshold=3)
    assert codes(w) == ["recipients", "new_recipients"]


def test_ids_count_toward_bulk_but_are_not_recipients():
    w = weigh(args={"ids": [str(i) for i in range(10)]}, threshold=10)
    assert w.audience is Weight.HEAVY and w.recipients == ()


@pytest.mark.parametrize("args", [
    {"attendees": [{"email": "A@X.com"}]},
    {"Recipients": "Kim <a@x.com>"},
    {"to": "a@x.com;"},
    {"invitees": ["  A@X.COM  "]},
    {"bcc": "\"a@x.com\""},
])
def test_recipient_extraction_accepts_the_real_shapes_and_normalizes(args):
    assert weigh(args=args).recipients == ("a@x.com",)


def test_duplicates_collapse_and_non_recipient_keys_are_ignored():
    w = weigh(args={"to": ["a@x.com", "A@x.com"], "cc": "a@x.com", "subject": "z@x.com", "note": ["q"]})
    assert w.recipients == ("a@x.com",)


def test_recipients_are_found_under_people_keys_and_nested_objects():
    args = {"guests": ["a@x.com"], "event": {"attendees": [{"email": "B@X.com"}], "invitees": "c@x.com"}}
    assert set(cw.extract_recipients(args)) == {"a@x.com", "b@x.com", "c@x.com"}


# 축 3: 얼마인가

def test_no_amount_is_light():
    assert weigh(kind="calendar_write", args={"summary": "x"}).amount is Weight.LIGHT


def test_spend_kind_without_a_readable_amount_is_heavy_unknown():
    w = weigh(kind="purchase", args={"item_id": "1"})
    assert w.amount is Weight.HEAVY and "amount_unknown" in codes(w)


@pytest.mark.parametrize("value", ["lots", True, {"v": 1}, -5, float("nan")])
def test_unreadable_amount_is_heavy_unknown(value):
    w = weigh(args={"budget": value})
    assert w.amount is Weight.HEAVY and codes(w) == ["amount_unknown"]


@pytest.mark.parametrize("value", [
    ABOVE_LIMIT, float(ABOVE_LIMIT), f"{ABOVE_LIMIT:,}", f"{ABOVE_LIMIT:,} won", f"${ABOVE_LIMIT:,}.00",
])
def test_amount_above_the_limit_is_heavy_and_shown_with_separators(value):
    w = weigh(args={"price": value})
    assert w.amount is Weight.HEAVY
    assert [(r.code, r.amount) for r in w.reasons] == [("amount", f"{ABOVE_LIMIT:,}")]
    assert w.amount_value == float(ABOVE_LIMIT)


def test_amount_at_the_limit_is_mid_and_one_above_is_heavy():
    at_limit = weigh(args={"amount": cw.MONEY_AUTO_LIMIT})
    assert at_limit.amount is Weight.MID
    assert weigh(args={"amount": cw.MONEY_AUTO_LIMIT + 1}).amount is Weight.HEAVY


def test_empty_amount_fields_count_as_absent_and_the_largest_field_decides():
    assert weigh(args={"budget": "", "price": None}).amount is Weight.LIGHT
    w = weigh(args={"budget": cw.MONEY_AUTO_LIMIT, "price": ABOVE_LIMIT})
    assert w.amount is Weight.HEAVY and w.amount_value == float(ABOVE_LIMIT)


@pytest.mark.parametrize("text, expected", [
    ("12,500", 12500.0), (" 12500 ", 12500.0), ("12,500.5", 12500.5), ("$12,500", 12500.0),
    ("KRW 12,500", 12500.0), ("12,500원", 12500.0), ("12,500 won", 12500.0), ("\u20a9 1,000", 1000.0),
])
def test_amount_text_is_read_when_only_a_unit_spaces_and_thousand_commas_surround_one_number(text, expected):
    assert cw.extract_amount({"price": text}).value == expected


@pytest.mark.parametrize("text", ["1e9", "1 000 000", "5.000.000", "99 + 999999"])
def test_a_string_amount_that_is_not_one_number_asks_even_for_a_trusted_allowed_kind(text):
    # 첫 숫자만 읽으면 1, 1, 5, 99 로 읽혀 한도 아래가 된다. 읽지 못하면 무겁게 본다.
    w = weigh(kind="file_write", args={"amount": text}, trust={"": entry()})
    assert w.amount is Weight.HEAVY and codes(w) == ["amount_unknown"]
    assert cw.decide(w, allowed=True, spot_check=w.spot_check) is Tier.ASK


@pytest.mark.parametrize("text", ["-5", "1,00", "$$5", "0x10", "1_000", "12,500 and 3", "9" * 400])
def test_other_malformed_amount_strings_are_unreadable(text):
    assert cw.extract_amount({"amount": text}).readable is False


def test_decimal_amount_is_shown_without_trailing_zeros():
    assert weigh(args={"price": "12.50"}).reasons[0].amount == "12.5"


# 축 4: 해 본 일인가

def test_kindless_tools_are_not_tracked():
    w = weigh(kind="", args={"x": 1})
    assert w.track is Weight.LIGHT and not w.spot_check


def test_no_history_is_heavy_first_time():
    w = weigh(kind="file_write")
    assert w.track is Weight.HEAVY and codes(w) == ["first_time"]


def test_trusted_entry_is_light():
    w = weigh(kind="file_write", trust={"": entry()})
    assert w.track is Weight.LIGHT and w.reasons == ()


def test_a_rejection_or_an_edit_breaks_trust():
    w = weigh(kind="file_write", trust={"": entry(streak=0)})
    assert w.track is Weight.HEAVY and codes(w) == ["first_time"]


def test_old_entries_expire_after_the_ttl():
    ttl = cw.TRUST_TTL_DAYS
    assert weigh(kind="file_write", trust={"": entry(last_days_ago=ttl - 0.1)}).track is Weight.LIGHT
    w = weigh(kind="file_write", trust={"": entry(last_days_ago=ttl + 0.1)})
    assert w.track is Weight.HEAVY and codes(w) == ["trust_expired"]


def test_every_recipient_needs_its_own_history():
    trust = {"a@x.com": entry()}
    both = weigh(kind="calendar_write", args={"attendees": ["a@x.com"]}, known=["a@x.com"], trust=trust)
    assert both.track is Weight.LIGHT
    one_missing = weigh(kind="calendar_write", args={"attendees": ["a@x.com", "b@x.com"]},
                        known=["a@x.com", "b@x.com"], trust=trust)
    assert one_missing.track is Weight.HEAVY


def test_a_new_recipient_already_says_first_time_so_the_reason_is_not_repeated():
    w = weigh(kind="calendar_write", args={"attendees": ["new@x.com"]})
    assert codes(w) == ["new_attendee"] and w.track is Weight.HEAVY


@pytest.mark.parametrize("uses,expected", [
    (0, False), (EVERY - 2, False), (EVERY - 1, True), (EVERY, False), (2 * EVERY - 1, True),
])
def test_spot_check_falls_on_every_nth_automatic_use(uses, expected):
    assert weigh(kind="file_write", trust={"": entry(auto_uses=uses)}).spot_check is expected


def test_spot_check_is_not_raised_for_untrusted_entries():
    assert weigh(kind="file_write", trust={"": entry(streak=0, auto_uses=EVERY - 1)}).spot_check is False


@pytest.mark.parametrize("bad", [None, {}, {"approved": "x", "streak": None}, {"approved": 2}, "junk", 7])
def test_malformed_history_is_no_history(bad):
    assert cw.trust_state(bad, NOW) == "none"


def light_weight(**axes):
    base = dict(reversibility=Weight.LIGHT, audience=Weight.LIGHT, amount=Weight.LIGHT, track=Weight.LIGHT)
    return cw.CallWeight(**{**base, **axes})


@pytest.mark.parametrize("axis", ["reversibility", "audience", "amount", "track"])
def test_any_heavy_axis_asks_even_when_allowed(axis):
    assert cw.decide(light_weight(**{axis: Weight.HEAVY}), allowed=True, spot_check=False) is Tier.ASK


def test_not_allowed_asks():
    assert cw.decide(light_weight(), allowed=False, spot_check=False) is Tier.ASK


def test_spot_check_asks():
    assert cw.decide(light_weight(), allowed=True, spot_check=True) is Tier.ASK


@pytest.mark.parametrize("axis", ["audience", "amount"])
def test_mid_axis_notifies(axis):
    assert cw.decide(light_weight(**{axis: Weight.MID}), allowed=True, spot_check=False) is Tier.NOTIFY


def test_all_light_runs_quietly():
    assert cw.decide(light_weight(), allowed=True, spot_check=False) is Tier.NONE


def test_end_to_end_tiers_for_the_three_motivating_calls():
    trust = {"": entry()}
    # 파일 쓰기, 칸 허락, 해 본 일: 조용히
    quiet = weigh(kind="file_write", risk="write", reason="write", args={"path": "a.txt"}, trust=trust)
    assert cw.decide(quiet, allowed=True, spot_check=quiet.spot_check) is Tier.NONE
    # 캘린더, 아는 참석자와 해 본 일: 하고 알림
    cal = weigh(kind="calendar_write", risk="destructive", reason="unverified",
                args={"attendees": ["a@x.com"]}, known=["a@x.com"], trust={"a@x.com": entry()})
    assert cw.decide(cal, allowed=True, spot_check=cal.spot_check) is Tier.NOTIFY
    # 외부 발송은 '알아서'여도 묻는다
    send = weigh(kind="external_send", risk="send_external", args={"to": ["a@x.com"]}, known=["a@x.com"],
                 trust={"a@x.com": entry()})
    assert cw.decide(send, allowed=True, spot_check=send.spot_check) is Tier.ASK


def test_allowed_kind_still_asks_for_a_big_amount():
    heavy = weigh(kind="file_write", args={"amount": ABOVE_LIMIT}, trust={"": entry()})
    assert cw.decide(heavy, allowed=True, spot_check=heavy.spot_check) is Tier.ASK


def test_calendar_attendees_are_called_attendees_not_recipients():
    new = cw.weigh(kind="calendar_write", args={"attendees": ["a@x.com"]}, now=0.0)
    two_new = cw.weigh(kind="calendar_write", args={"attendees": ["a@x.com", "b@x.com"]}, now=0.0)
    known = cw.weigh(kind="calendar_write", args={"attendees": ["a@x.com"]}, is_known=lambda _a: True, now=0.0)

    assert codes(new) == ["new_attendee"] and new.track is Weight.HEAVY
    assert [(r.code, r.count) for r in two_new.reasons] == [("new_attendees", 2)]
    assert codes(known)[0] == "attendees"
