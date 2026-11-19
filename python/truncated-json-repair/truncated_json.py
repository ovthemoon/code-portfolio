"""토큰 상한에 잘린 모델 JSON을 최대한 살려서 읽는다.

모델 응답이 서버의 출력 토큰 상한에 걸려 중간에서 끊기면 ``json.loads`` 는 실패한다.
그런데 앞쪽의 완성된 항목(예: 질문 목록의 첫 질문)은 멀쩡하다. 그래서 마지막으로 닫힌
컨테이너(``}`` 또는 ``]``)까지 자르고, 열려 있던 괄호를 역순으로 닫아 다시 파싱한다.
"""

from __future__ import annotations

import json
import re
from typing import Any


def repair_truncated_json(s: str) -> str:
    """잘린 JSON 최선 복구.

    마지막으로 닫힌 컨테이너까지 자르고 남은 스택을 닫는다. 문자열 경계를 존중하며,
    불완전한 꼬리(끊긴 항목, 남은 쉼표)는 버린다. 완성된 항목은 살아남는다.
    ``s`` 는 첫 ``{`` 부터의 슬라이스다.
    """
    stack: list[str] = []
    in_str = False
    escape = False
    cut = -1
    cut_stack: list[str] = []
    for i, ch in enumerate(s):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack:
                stack.pop()
            cut = i                    # 컨테이너가 닫힌 안전한 절단점
            cut_stack = list(stack)
    if cut < 0:
        return s                       # 닫힌 컨테이너가 없다. 복구할 수 없다(파싱은 실패한다)
    return s[:cut + 1] + "".join(reversed(cut_stack))


def parse_model_json(text: str) -> dict[str, Any] | None:
    """모델 응답에서 JSON 객체를 꺼낸다. 실패하면 None.

    1. 코드 펜스를 걷고 첫 ``{`` 부터 마지막 ``}`` 까지를 파싱한다.
    2. 실패하면 잘린 응답으로 보고 복구한 뒤 한 번 더 파싱한다.
    """
    if not text:
        return None
    cleaned = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "")
    start = cleaned.find("{")
    if start < 0:
        return None
    obj = None
    end = cleaned.rfind("}")
    if end > start:
        try:
            obj = json.loads(cleaned[start:end + 1])
        except ValueError:
            obj = None
    if obj is None:
        try:
            obj = json.loads(repair_truncated_json(cleaned[start:]))
        except ValueError:
            return None
    return obj if isinstance(obj, dict) else None
