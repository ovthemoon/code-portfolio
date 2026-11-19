"""잘린 JSON 복구: 완성된 항목은 살리고, 살릴 게 없으면 None."""

from __future__ import annotations

import json

import pytest

from truncated_json import parse_model_json, repair_truncated_json

Q1 = {"id": "channel", "q": "Which channel?", "options": ["#general", "DM"], "required": True}
Q2 = {"id": "time", "q": "What time in the evening?", "sub": "Pick one", "required": False}
Q3 = {"id": "format", "q": "Short or long?", "options": ["short", "long"], "required": False}


def test_complete_json_is_parsed_as_is():
    text = json.dumps({"needs_clarification": False, "questions": [Q1]})
    assert parse_model_json(text) == {"needs_clarification": False, "questions": [Q1]}


def test_code_fence_and_surrounding_text_are_ignored():
    text = 'Here you go:\n```json\n{"a": 1}\n```\nDone.'
    assert parse_model_json(text) == {"a": 1}


def test_cut_inside_a_string_keeps_the_completed_question():
    truncated = (
        '```json\n{\n  "needs_clarification": true,\n  "questions": [\n'
        '    {"id": "channel", "q": "Which channel?", "required": true, "options": ["#general", "DM"]},\n'
        '    {"id": "time", "q": "What time in the eve'
    )
    result = parse_model_json(truncated)
    assert result == {
        "needs_clarification": True,
        "questions": [{"id": "channel", "q": "Which channel?", "required": True,
                       "options": ["#general", "DM"]}],
    }


def test_cut_after_a_key_without_a_value_drops_the_dangling_tail():
    truncated = '{"questions": [{"id": "a", "q": "x"}, {"id": "b", "q": "y"}, {"id"'
    assert parse_model_json(truncated) == {"questions": [{"id": "a", "q": "x"}, {"id": "b", "q": "y"}]}


def test_open_brackets_are_closed_in_reverse_order():
    assert repair_truncated_json('{"a": [{"b": [1, 2]}, {"c"') == '{"a": [{"b": [1, 2]}]}'


def test_a_closed_inner_object_survives_when_the_outer_one_is_cut():
    truncated = '{"spec": {"frequency": "daily"}, "questions": [{"id": "x", "q": "tru'
    assert parse_model_json(truncated) == {"spec": {"frequency": "daily"}}


def test_brackets_and_escaped_quotes_inside_strings_do_not_confuse_the_scan():
    tricky = {"q": 'use } and ] and \\" here', "id": "a"}
    text = '{"questions": [' + json.dumps(tricky) + ', {"id": "b", "q": "cut'
    assert parse_model_json(text) == {"questions": [tricky]}


def test_nothing_closed_means_nothing_to_recover():
    truncated = '{"needs_clarification": true, "questions": [{"id": "x", "q": "Which chan'
    assert repair_truncated_json(truncated) == truncated
    assert parse_model_json(truncated) is None


@pytest.mark.parametrize("text", ["", "not json at all", "[1, 2, 3]", "{broken: json}"])
def test_garbage_returns_none(text):
    assert parse_model_json(text) is None


def test_every_cut_after_the_first_question_yields_questions_from_the_original():
    document = json.dumps({"needs_clarification": True, "questions": [Q1, Q2, Q3]})
    first_question_end = document.index(json.dumps(Q1)) + len(json.dumps(Q1))
    all_questions = [Q1, Q2, Q3]

    for cut in range(first_question_end, len(document)):
        result = parse_model_json(document[:cut])
        assert result is not None, f"cut at {cut}"
        got = result["questions"]
        assert 1 <= len(got) <= 3
        assert got[:-1] == all_questions[:len(got) - 1], f"cut at {cut}"   # 마지막 앞은 항상 온전하다
        original = all_questions[len(got) - 1]
        assert got[-1].items() <= original.items(), f"cut at {cut}"        # 마지막은 원본의 부분집합이다


def test_known_limit_last_item_may_lose_the_fields_after_its_last_closed_array():
    """절단점이 안쪽 배열의 닫힘일 수 있다. 그 항목은 살지만 뒤쪽 필드는 잃는다."""
    truncated = '{"questions": [{"id": "a", "options": ["x", "y"], "required": tr'
    assert parse_model_json(truncated) == {"questions": [{"id": "a", "options": ["x", "y"]}]}


def test_cuts_never_raise():
    document = json.dumps({"questions": [Q1, Q2], "spec": {"hour": 9}})
    for cut in range(len(document) + 1):
        parse_model_json(document[:cut])
