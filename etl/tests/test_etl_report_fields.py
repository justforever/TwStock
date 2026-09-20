"""find_field_all 函式的單元測試。"""

import pytest

from twstock_etl.errors import SourceFormatError
from twstock_etl.sources.report import find_field_all, find_field_all_optional


class TestFindFieldAll:
    """測試 find_field_all 函式。"""

    def test_find_field_all_全部關鍵字都要命中(self) -> None:
        """測試必須同時包含所有關鍵字。"""
        fields = [
            "外陸資買進股數(不含外資自營商)",
            "外資自營商買進股數",
        ]
        result = find_field_all(fields, "買進", "不含外資自營商")
        assert result == 0

    def test_find_field_all_exclude_排除欄位(self) -> None:
        """測試排除關鍵字。"""
        fields = ["外資自營商買進股數", "自營商買進股數(自行買賣)"]
        result = find_field_all(fields, "自營商", "買進", exclude=("外資",))
        assert result == 1

    def test_find_field_all_找不到拋_SourceFormatError(self) -> None:
        """測試找不到時拋異常。"""
        fields = ["投信買進股數", "投信賣出股數"]
        with pytest.raises(SourceFormatError):
            find_field_all(fields, "融資", "買進")

    def test_find_field_all_optional_找不到回_None(self) -> None:
        """測試 optional 版本找不到時回 None。"""
        fields = ["投信買進股數", "投信賣出股數"]
        result = find_field_all_optional(fields, "融資", "買進")
        assert result is None

    def test_欄位名含_HTML_標籤也找得到(self) -> None:
        """測試欄位名包含 HTML 標籤時能正常比對。"""
        fields = ["<b>投信買進股數</b>"]
        result = find_field_all(fields, "投信", "買進")
        assert result == 0
