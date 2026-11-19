"""is_path_within 경계 위생 테스트.

핵심 회귀 가드: 형제 접두사 버그(/a/agent1 이 /a/agent1-evil 을 통과)와 한글 NFC/NFD 함정.
"""

from __future__ import annotations

import os
import unicodedata

import pytest

from pathguard import is_path_within, normalize_path_for_compare


def naive_contains(base: str, target: str) -> bool:
    """고치기 전 패턴. 형제 접두사 버그를 보이기 위한 기준선이다."""
    return os.path.realpath(target).startswith(os.path.realpath(base))


def test_target_inside_is_within(tmp_path):
    base = tmp_path / "ws"
    assert is_path_within(str(base), str(base / "sub" / "a.txt")) is True


def test_base_itself_is_within(tmp_path):
    base = tmp_path / "ws"
    assert is_path_within(str(base), str(base)) is True


def test_outside_is_rejected(tmp_path):
    base = tmp_path / "ws"
    assert is_path_within(str(base), str(tmp_path / "other" / "x.txt")) is False


def test_filesystem_root_as_base_accepts_everything_below_it():
    root = os.path.abspath(os.sep)
    assert is_path_within(root, os.path.join(root, "anything", "x.txt")) is True


def test_naive_prefix_check_lets_the_sibling_through(tmp_path):
    base = tmp_path / "agent1"
    sibling = tmp_path / "agent1-evil" / "secret"
    assert naive_contains(str(base), str(sibling)) is True  # 버그
    assert is_path_within(str(base), str(sibling)) is False  # 고침


def test_sibling_with_shared_prefix_and_no_separator_is_rejected(tmp_path):
    base = tmp_path / "ws"
    assert is_path_within(str(base), str(tmp_path / "wssuffix")) is False


def test_dotdot_traversal_is_rejected(tmp_path):
    base = tmp_path / "ws"
    base.mkdir()
    assert is_path_within(str(base), str(base / ".." / "escape.txt")) is False


def test_dotdot_that_stays_inside_is_accepted(tmp_path):
    base = tmp_path / "ws"
    (base / "a").mkdir(parents=True)
    assert is_path_within(str(base), str(base / "a" / ".." / "b.txt")) is True


@pytest.mark.skipif(os.name == "nt", reason="Windows 의 심볼릭 링크 생성은 권한이 필요하다")
def test_symlink_pointing_outside_is_rejected(tmp_path):
    base = tmp_path / "ws"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = base / "link"
    os.symlink(str(outside), str(link))
    # 워크스페이스 안의 링크가 밖을 가리키면 realpath 로 풀린 뒤 거부된다.
    assert is_path_within(str(base), str(link / "x.txt")) is False


def test_korean_nfc_and_nfd_name_the_same_folder(tmp_path):
    nfc_base = str(tmp_path / "문서")
    nfd_base = unicodedata.normalize("NFD", nfc_base)
    assert nfd_base != nfc_base  # 전제: 바이트가 실제로 다르다
    assert is_path_within(nfd_base, nfc_base + "/보고서.txt") is True
    assert is_path_within(nfc_base, nfd_base + "/보고서.txt") is True


def test_korean_sibling_is_still_rejected(tmp_path):
    base = unicodedata.normalize("NFD", str(tmp_path / "문서"))
    sibling = str(tmp_path / "문서-비밀") + "/x.txt"  # NFC
    assert is_path_within(base, sibling) is False


def test_case_difference_is_ignored(tmp_path):
    assert is_path_within(str(tmp_path / "Docs"), str(tmp_path / "docs" / "a.txt")) is True


def test_tilde_in_base_is_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert is_path_within("~/ws", str(tmp_path / "ws" / "a.txt")) is True


def test_normalize_collapses_nfc_and_nfd():
    nfc = "문서"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert normalize_path_for_compare(nfc) == normalize_path_for_compare(nfd)
