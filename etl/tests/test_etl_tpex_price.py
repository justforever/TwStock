"""上櫃日成交 parser 單元測試。"""

import json
import pathlib
from datetime import date
from decimal import Decimal

import httpx
import pytest

from twstock_etl.errors import SourceFormatError
from twstock_etl.sources.tpex_price import fetch_tpex_daily, parse_tpex_daily

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestParseTpexDaily:
    """測試 parse_tpex_daily 函式。"""

    def test_parse_new_format(self) -> None:
        """應正確解析新版 fixture。"""
        payload = json.loads((FIXTURE_DIR / "TPEx_price_20260918.json").read_text())
        records = parse_tpex_daily(payload, date(2026, 9, 18))

        # 應有 4 筆（5347 無成交被跳過）
        assert len(records) == 4

        # 3105 的檢驗
        tpex_3105 = next(r for r in records if r.stock_id == "3105")
        assert tpex_3105.close == Decimal("349.00")
        assert tpex_3105.change == Decimal("-3.00")
        assert tpex_3105.source == "TPEx"

    def test_parse_legacy_format(self) -> None:
        """應正確解析舊版 fixture。"""
        payload = json.loads((FIXTURE_DIR / "TPEx_price_legacy_sample.json").read_text())
        records = parse_tpex_daily(payload, date(2026, 9, 18))

        # 應有 1 筆（5347 無成交被跳過）
        assert len(records) == 1

        # 3105 的檢驗
        tpex_3105 = records[0]
        assert tpex_3105.close == Decimal("349.00")

    def test_report_date_mismatch_raises_error(self) -> None:
        """reportDate 與傳入日期不符應拋 SourceFormatError。"""
        payload = json.loads((FIXTURE_DIR / "TPEx_price_legacy_sample.json").read_text())

        with pytest.raises(SourceFormatError, match="不符"):
            parse_tpex_daily(payload, date(2026, 9, 17))

    def test_fetch_tpex_daily_fallback_to_legacy(self) -> None:
        """新版失敗應自動退回舊版。"""
        call_count = {"new": 0, "legacy": 0}

        def transport_callback(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)

            if "/afterTrading/otc" in url_str:
                call_count["new"] += 1
                # 新版端點回 500
                return httpx.Response(500)
            elif "/daily_close_quotes/" in url_str:
                call_count["legacy"] += 1
                # 舊版端點回傳 legacy fixture
                payload = json.loads((FIXTURE_DIR / "TPEx_price_legacy_sample.json").read_text())
                return httpx.Response(200, json=payload)
            else:
                return httpx.Response(404)

        transport = httpx.MockTransport(transport_callback)
        client = httpx.Client(transport=transport)

        result = fetch_tpex_daily(date(2026, 9, 18), client=client)

        # 應試過新版和舊版
        assert call_count["new"] == 1
        assert call_count["legacy"] == 1
        assert "aaData" in result
