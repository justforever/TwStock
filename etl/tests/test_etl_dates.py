"""日期解析測試。"""

from datetime import date

import pytest

from twstock_etl.dates import parse_tw_date


class TestParseTwDate:
    """parse_tw_date 測試。"""

    # 西元 YYYY-MM-DD 格式
    def test_western_dash_format(self) -> None:
        assert parse_tw_date("2026-01-05") == date(2026, 1, 5)
        assert parse_tw_date("2000-12-31") == date(2000, 12, 31)

    # 西元 YYYY/MM/DD 格式
    def test_western_slash_format(self) -> None:
        assert parse_tw_date("2026/01/05") == date(2026, 1, 5)
        assert parse_tw_date("2000/12/31") == date(2000, 12, 31)

    # 西元 8 位數字 YYYYMMDD
    def test_western_8digit(self) -> None:
        assert parse_tw_date("20260105") == date(2026, 1, 5)
        assert parse_tw_date("20001231") == date(2000, 12, 31)

    # 民國 7 位數字 RRRMMDD（前 3 位民國年 +1911）
    def test_roc_7digit(self) -> None:
        assert parse_tw_date("1150105") == date(2026, 1, 5)
        assert parse_tw_date("0890612") == date(2000, 6, 12)

    # 民國 6 位數字 RRMMDD（前 2 位民國年 +1911）
    def test_roc_6digit(self) -> None:
        assert parse_tw_date("990105") == date(2010, 1, 5)
        assert parse_tw_date("001231") == date(1911, 12, 31)

    # 民國 RRR/MM/DD 格式
    def test_roc_slash_3digit(self) -> None:
        assert parse_tw_date("115/01/05") == date(2026, 1, 5)
        assert parse_tw_date("089/06/12") == date(2000, 6, 12)

    # 民國 RR/M/D 格式
    def test_roc_slash_2digit(self) -> None:
        assert parse_tw_date("99/1/5") == date(2010, 1, 5)
        assert parse_tw_date("00/12/31") == date(1911, 12, 31)

    # 無效日期
    def test_invalid_date_raises(self) -> None:
        with pytest.raises(ValueError, match="無法解析日期"):
            parse_tw_date("2026-02-30")

    # 空字串
    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="無法解析日期"):
            parse_tw_date("")

    # 特殊值
    def test_special_value_raises(self) -> None:
        with pytest.raises(ValueError, match="無法解析日期"):
            parse_tw_date("--")

    # 非日期字串
    def test_non_date_string_raises(self) -> None:
        with pytest.raises(ValueError, match="無法解析日期"):
            parse_tw_date("abc")

    # 前後空白
    def test_whitespace_stripped(self) -> None:
        assert parse_tw_date("  2026-01-05  ") == date(2026, 1, 5)
