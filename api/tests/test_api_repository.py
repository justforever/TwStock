import pytest

from twstock_api.repository import escape_like, normalize_query


def test_escape_like_percent() -> None:
    """測試 % 跳脫."""
    assert escape_like("50%") == "50!%"


def test_escape_like_underscore() -> None:
    """測試 _ 跳脫."""
    assert escape_like("a_b") == "a!_b"


def test_escape_like_exclamation() -> None:
    """測試 ! 跳脫."""
    assert escape_like("x!y") == "x!!y"


def test_escape_like_multiple() -> None:
    """測試多個特殊字元."""
    assert escape_like("!%") == "!!!%"


def test_normalize_query_strip() -> None:
    """測試 strip."""
    assert normalize_query(" 臺積 ") == "台積"


def test_normalize_query_replace_taiwan() -> None:
    """測試臺→台 轉換."""
    assert normalize_query("臺企") == "台企"
