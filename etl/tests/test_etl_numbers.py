"""數值清洗工具單元測試。"""

from decimal import Decimal

import pytest

from twstock_etl.errors import SourceFormatError
from twstock_etl.numbers import clean_cell, parse_decimal, parse_int, parse_sign


class TestCleanCell:
    """測試 clean_cell 函式。"""

    def test_clean_html_tags(self) -> None:
        """應移除 HTML 標籤。"""
        assert clean_cell("<p style= color:red>+</p>") == ""

    def test_clean_full_width_space(self) -> None:
        """應移除全形空白。"""
        assert clean_cell("　123　") == "123"

    def test_clean_comma(self) -> None:
        """應移除千分位逗號。"""
        assert clean_cell("1,234.56") == "1234.56"

    def test_strip_whitespace(self) -> None:
        """應移除前後空白。"""
        assert clean_cell("  123  ") == "123"

    def test_remove_leading_plus(self) -> None:
        """應移除開頭加號。"""
        assert clean_cell("+123") == "123"

    def test_keep_minus_sign(self) -> None:
        """應保留負號。"""
        assert clean_cell("-123") == "-123"

    def test_double_minus(self) -> None:
        """應保留雙減號（視為 NULL_TOKEN）。"""
        assert clean_cell("--") == "--"


class TestParseDecimal:
    """測試 parse_decimal 函式。"""

    def test_parse_simple_decimal(self) -> None:
        """應解析簡單數字。"""
        assert parse_decimal("1234.56") == Decimal("1234.56")

    def test_parse_with_comma(self) -> None:
        """應解析帶逗號的數字。"""
        assert parse_decimal("1,234.56") == Decimal("1234.56")

    def test_parse_negative(self) -> None:
        """應解析負數。"""
        assert parse_decimal("-1.5") == Decimal("-1.5")

    def test_null_token_double_dash(self) -> None:
        """-- 應回傳 None。"""
        assert parse_decimal("--") is None

    def test_null_token_empty(self) -> None:
        """空字串應回傳 None。"""
        assert parse_decimal("") is None

    def test_null_token_x(self) -> None:
        """X 應回傳 None。"""
        assert parse_decimal("X") is None

    def test_invalid_format(self) -> None:
        """無法解析應拋 SourceFormatError。"""
        with pytest.raises(SourceFormatError):
            parse_decimal("abc")


class TestParseInt:
    """測試 parse_int 函式。"""

    def test_parse_int(self) -> None:
        """應解析整數。"""
        assert parse_int("1,000") == 1000

    def test_parse_int_from_decimal(self) -> None:
        """應從 Decimal 轉成整數。"""
        assert parse_int("1234.56") == 1234

    def test_null_token(self) -> None:
        """NULL_TOKEN 應回傳 None。"""
        assert parse_int("--") is None


class TestParseSign:
    """測試 parse_sign 函式。"""

    def test_positive_sign_html(self) -> None:
        """HTML 紅色加號應回傳 1。"""
        assert parse_sign("<p style= color:red>+</p>") == 1

    def test_positive_sign_text(self) -> None:
        """文本加號應回傳 1。"""
        assert parse_sign("+") == 1

    def test_negative_sign_html(self) -> None:
        """HTML 綠色減號應回傳 -1。"""
        assert parse_sign("<p style= color:green>-</p>") == -1

    def test_negative_sign_text(self) -> None:
        """文本減號應回傳 -1。"""
        assert parse_sign("-") == -1

    def test_no_sign_x(self) -> None:
        """X 應回傳 0。"""
        assert parse_sign("X") == 0

    def test_no_sign_empty(self) -> None:
        """空字串應回傳 0。"""
        assert parse_sign("") == 0
