"""경로 포함(containment) 검사. 워크스페이스 경계를 정하는 단 하나의 함수.

파일 도구들이 저마다 ``os.path.realpath(p).startswith(os.path.realpath(workspace))`` 를
복붙해 쓰고 있었다. 이 패턴에는 형제 접두사 버그가 있다. 끝에 구분자가 없어서
워크스페이스 ``/a/agent1`` 이 형제 디렉터리 ``/a/agent1-evil`` 까지 통과시킨다.
또 유니코드와 대소문자 정규화가 없어 macOS(파일명을 NFD 로 저장)에서 allowlist 루트가
NFC 이면 정상적인 한글 폴더가 거부된다.

이 모듈은 둘을 한 번에 닫는다.

남은 위험: TOCTOU 와 하드링크는 다루지 않는다. 임의 셸이 살아 있는 한 이 검사는
어차피 우회되므로, 이 함수는 구조화된 파일 도구의 경계 위생만 책임진다. 진짜 경계는
OS 격리가 있어야 성립한다.
"""

from __future__ import annotations

import os
import unicodedata


def normalize_path_for_compare(path: str) -> str:
    """경로 비교용 정규화: NFC + casefold.

    - NFC: macOS 는 파일명을 NFD 로 저장한다. 한쪽이 NFC, 한쪽이 NFD 면 바이트 비교가
      어긋나 정상 폴더가 거부된다. 양쪽을 NFC 로 모아 이 함정을 없앤다.
    - casefold: APFS 기본은 대소문자를 구분하지 않는다. 실제 동작에 맞춰 경계 검사도
      대소문자를 접는다. 대소문자를 구분하는 파일시스템에서는 조금 관대해지지만, 최종
      판정은 open() 이 하므로 방어를 겹치는 쪽이라 안전하다.
    """
    return unicodedata.normalize("NFC", path).casefold()


def is_path_within(base: str, target: str) -> bool:
    """``target`` 이 ``base`` 디렉터리 안(또는 base 자신)인지.

    1. 양쪽을 ``realpath`` 로 정규화한다. 심볼릭 링크를 풀고 ``..`` 를 접어 우회를 막는다.
       base 는 ``~`` 도 확장한다.
    2. NFC + casefold 로 정규화한 뒤 비교한다.
    3. ``target == base`` 이거나 ``target`` 이 ``base + os.sep`` 로 시작하면 내부다.
       구분자까지 붙여 비교하므로 ``/a/agent1`` 이 ``/a/agent1-evil`` 을 통과시키지 않는다.

    target 은 존재하지 않아도 된다(realpath 는 없는 경로도 정규화한다). 워크스페이스 안의
    심볼릭 링크가 밖을 가리키면 실제 대상으로 해석되어 False 가 된다.
    """
    base_real = os.path.realpath(os.path.expanduser(base))
    target_real = os.path.realpath(target)

    b = normalize_path_for_compare(base_real)
    t = normalize_path_for_compare(target_real)

    if t == b:
        return True
    # base 가 파일시스템 루트("/")인 퇴화 경우. 이미 구분자로 끝나므로 접두사만 본다.
    sep = normalize_path_for_compare(os.sep)
    if b.endswith(sep):
        return t.startswith(b)
    return t.startswith(b + sep)
