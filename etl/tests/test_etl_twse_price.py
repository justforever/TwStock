"""上市日成交 parser 單元測試。"""

import json
import pathlib
from datetime import date
from decimal import Decimal

import httpx
import pytest

from twstock_etl.errors import SourceFormatError
from twstock_etl.sources.twse_price import fetch_twse_daily, parse_twse_daily

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestParseTwseDaily:
    """測試 parse_twse_daily 函式。"""

    def test_parse_complete_fixture(self) -> None:
        """應正確解析完整 fixture。"""
        payload = json.loads((FIXTURE_DIR / "TWSE_price_20260918.json").read_text())
        records = parse_twse_daily(payload, date(2026, 9, 18))

        # 應有 5 筆（2834 無成交被跳過）
        assert len(records) == 5

        # 2330 的檢驗
        twse_2330 = next(r for r in records if r.stock_id == "2330")
        assert twse_2330.close == Decimal("1008.00")
        assert twse_2330.volume == 30000000
        assert twse_2330.change == Decimal("13.00")
        assert twse_2330.source == "TWSE"
        assert twse_2330.transactions == 35000
        assert twse_2330.turnover == Decimal("30000000000")

        # 0050 的綠色減號檢驗
        twse_0050 = next(r for r in records if r.stock_id == "0050")
        assert twse_0050.change == Decimal("-0.50")

    def test_empty_data_raises_error(self) -> None:
        """資料表為空應拋 SourceFormatError。"""
        payload = json.loads((FIXTURE_DIR / "TWSE_price_20260918.json").read_text())
        payload["tables"][1]["data"] = []

        with pytest.raises(SourceFormatError, match="資料表為空"):
            parse_twse_daily(payload, date(2026, 9, 18))

    def test_invalid_stat_raises_error(self) -> None:
        """stat 非 OK 應拋 SourceFormatError。"""
        payload = json.loads((FIXTURE_DIR / "TWSE_price_20260918.json").read_text())
        payload["stat"] = "很抱歉"

        with pytest.raises(SourceFormatError, match="stat 非 OK"):
            parse_twse_daily(payload, date(2026, 9, 18))

    def test_fetch_twse_daily_with_mock(self) -> None:
        """應驗證 fetch_twse_daily 帶出正確的 params。"""
        def transport_callback(request: httpx.Request) -> httpx.Response:
            # 驗證參數
            assert request.url.params["date"] == "20260918"
            assert request.url.params["type"] == "ALLBUT0999"
            assert request.url.params["response"] == "json"

            # 回傳 fixture
            payload = json.loads((FIXTURE_DIR / "TWSE_price_20260918.json").read_text())
            return httpx.Response(200, json=payload)

        transport = httpx.MockTransport(transport_callback)
        client = httpx.Client(transport=transport)

        result = fetch_twse_daily(date(2026, 9, 18), client=client)
        assert result["stat"] == "OK"
        assert "tables" in result
