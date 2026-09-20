"""三大法人 parser 的測試。"""

import json
from datetime import date

import httpx
import pytest

from twstock_etl.errors import SourceFormatError
from twstock_etl.sources.institutional import (
    parse_twse_institutional,
    parse_tpex_institutional,
    fetch_tpex_institutional,
)


class TestInstitutionalParser:
    """測試三大法人 parser。"""

    @pytest.fixture
    def twse_fixture_20260916(self) -> dict:
        """載入 TWSE 09-16 fixture。"""
        with open("etl/tests/fixtures/TWSE_institutional_20260916.json") as f:
            return json.load(f)

    @pytest.fixture
    def twse_fixture_20260917(self) -> dict:
        """載入 TWSE 09-17 fixture。"""
        with open("etl/tests/fixtures/TWSE_institutional_20260917.json") as f:
            return json.load(f)

    @pytest.fixture
    def twse_fixture_20260918(self) -> dict:
        """載入 TWSE 09-18 fixture。"""
        with open("etl/tests/fixtures/TWSE_institutional_20260918.json") as f:
            return json.load(f)

    @pytest.fixture
    def tpex_fixture_20260918(self) -> dict:
        """載入 TPEx 09-18 fixture。"""
        with open("etl/tests/fixtures/TPEx_institutional_20260918.json") as f:
            return json.load(f)

    @pytest.fixture
    def tpex_legacy_fixture(self) -> dict:
        """載入 TPEx 舊版 fixture。"""
        with open("etl/tests/fixtures/TPEx_institutional_legacy_sample.json") as f:
            return json.load(f)

    def test_上市解析四筆(self, twse_fixture_20260916: dict) -> None:
        """測試上市解析結果有四筆（未知代號不過濾）。"""
        records = parse_twse_institutional(twse_fixture_20260916, date(2026, 9, 16))
        assert len(records) == 4

    def test_上市_2330_三天的數值(
        self,
        twse_fixture_20260916: dict,
        twse_fixture_20260917: dict,
        twse_fixture_20260918: dict,
    ) -> None:
        """測試上市 2330 三天的計算值。"""
        # 2026-09-16
        records = parse_twse_institutional(twse_fixture_20260916, date(2026, 9, 16))
        r = [x for x in records if x.stock_id == "2330"][0]
        assert r.foreign_buy == 14_000_000
        assert r.foreign_sell == 9_000_000
        assert r.foreign_net == 5_000_000
        assert r.trust_net == 1_000_000
        assert r.dealer_buy == 800_000
        assert r.dealer_sell == 1_100_000
        assert r.dealer_net == -300_000
        assert r.total_net == 5_700_000

        # 2026-09-17
        records = parse_twse_institutional(twse_fixture_20260917, date(2026, 9, 17))
        r = [x for x in records if x.stock_id == "2330"][0]
        assert r.foreign_net == 8_000_000
        assert r.trust_net == -2_000_000
        assert r.dealer_net == 200_000
        assert r.total_net == 6_200_000

        # 2026-09-18
        records = parse_twse_institutional(twse_fixture_20260918, date(2026, 9, 18))
        r = [x for x in records if x.stock_id == "2330"][0]
        assert r.foreign_net == 12_000_000
        assert r.trust_net == 2_000_000
        assert r.dealer_net == -500_000
        assert r.total_net == 13_500_000

    def test_上市_2317_全零也會被收(self, twse_fixture_20260918: dict) -> None:
        """測試 2317 全零也會被收進結果。"""
        records = parse_twse_institutional(twse_fixture_20260918, date(2026, 9, 18))
        r = [x for x in records if x.stock_id == "2317"]
        assert len(r) == 1
        assert r[0].foreign_net == 0
        assert r[0].trust_net == 0
        assert r[0].dealer_net == 0
        assert r[0].total_net == 0

    def test_上櫃新版解析三筆與_3105_數值(self, tpex_fixture_20260918: dict) -> None:
        """測試上櫃新版端點解析結果。"""
        records = parse_tpex_institutional(tpex_fixture_20260918, date(2026, 9, 18))
        assert len(records) == 3

        r = [x for x in records if x.stock_id == "3105"][0]
        assert r.foreign_net == 550_000
        assert r.trust_net == 100_000
        assert r.dealer_net == -20_000
        assert r.total_net == 630_000
        assert r.source == "TPEx"

    def test_上櫃舊版備援解析結果與新版一致(self, tpex_legacy_fixture: dict) -> None:
        """測試上櫃舊版備援端點解析結果與新版相同。"""
        records = parse_tpex_institutional(tpex_legacy_fixture, date(2026, 9, 18))
        r = [x for x in records if x.stock_id == "3105"][0]
        assert r.foreign_net == 550_000
        assert r.trust_net == 100_000
        assert r.dealer_net == -20_000
        assert r.total_net == 630_000
        assert r.source == "TPEx"

    def test_缺少投信欄位拋_SourceFormatError(self, twse_fixture_20260918: dict) -> None:
        """測試缺少投信欄位時拋異常。"""
        payload = twse_fixture_20260918.copy()
        payload["fields"] = [f.replace("投信買進股數", "XX") for f in payload["fields"]]
        with pytest.raises(SourceFormatError):
            parse_twse_institutional(payload, date(2026, 9, 18))

    def test_data_為空拋_SourceFormatError(self, twse_fixture_20260918: dict) -> None:
        """測試資料為空時拋異常。"""
        payload = twse_fixture_20260918.copy()
        payload["data"] = []
        with pytest.raises(SourceFormatError):
            parse_twse_institutional(payload, date(2026, 9, 18))

    def test_fetch_上櫃新版失敗會退回舊版(self, tpex_legacy_fixture: dict, caplog: pytest.LogCaptureFixture) -> None:  # type: ignore
        """測試上櫃新版失敗時自動退回舊版。"""
        # 建立 mock transport：新版 500、舊版正常
        def mock_transport(request: httpx.Request) -> httpx.Response:
            if "insti/dailyTrade" in str(request.url):
                # 新版端點 → 500 error
                return httpx.Response(500)
            elif "3itrade_hedge_result" in str(request.url):
                # 舊版端點 → 正常回應
                return httpx.Response(
                    200,
                    json=tpex_legacy_fixture,
                    headers={"content-type": "application/json"},
                )
            else:
                return httpx.Response(404)

        client = httpx.Client(transport=httpx.MockTransport(mock_transport))
        result = fetch_tpex_institutional(date(2026, 9, 18), client=client)
        assert "aaData" in result
        assert len(result["aaData"]) == 1
        assert "warning" in caplog.text.lower() or "新版" in caplog.text
