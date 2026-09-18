"""加權指數 parser 單元測試。"""

import json
import pathlib
from datetime import date
from decimal import Decimal

import pytest

from twstock_etl.errors import SourceFormatError
from twstock_etl.sources.twse_index import parse_taiex_month

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestParseTaiexMonth:
    """測試 parse_taiex_month 函式。"""

    def test_parse_complete_fixture(self) -> None:
        """應正確解析完整 fixture。"""
        payload = json.loads((FIXTURE_DIR / "TAIEX_index_202609.json").read_text())
        records = parse_taiex_month(payload, 2026, 9)

        # 應有 3 筆
        assert len(records) == 3

        # 最後一筆（2026-09-18）的檢驗
        last_record = records[-1]
        assert last_record.trade_date == date(2026, 9, 18)
        assert last_record.close == Decimal("24780.00")
        assert last_record.index_id == "TAIEX"
        assert last_record.volume is None

    def test_wrong_month_raises_error(self) -> None:
        """要求月份無資料應拋 SourceFormatError。"""
        payload = json.loads((FIXTURE_DIR / "TAIEX_index_202609.json").read_text())

        with pytest.raises(SourceFormatError, match="不含 2026-08"):
            parse_taiex_month(payload, 2026, 8)

    def test_sorted_by_date(self) -> None:
        """應按 trade_date 升冪排序。"""
        payload = json.loads((FIXTURE_DIR / "TAIEX_index_202609.json").read_text())
        records = parse_taiex_month(payload, 2026, 9)

        for i in range(len(records) - 1):
            assert records[i].trade_date < records[i + 1].trade_date
