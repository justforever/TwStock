"""融資融券 parser 測試。"""

import json
from datetime import date

import pytest
import httpx

from twstock_etl.errors import SourceFormatError
from twstock_etl.sources.margin import (
    parse_twse_margin,
    parse_tpex_margin,
    fetch_tpex_margin,
    TWSE_MARGIN_REQUIRED_FIELDS,
    TPEX_MARGIN_REQUIRED_FIELDS,
)


def test_上市解析四筆():
    """測試解析上市融資融券 fixture，應得到 4 筆（含未知代號 9999）。"""
    with open("etl/tests/fixtures/TWSE_margin_20260918.json") as f:
        payload = json.load(f)
    records = parse_twse_margin(payload, date(2026, 9, 18))
    assert len(records) == 4


def test_上市_2330_三天的餘額():
    """測試上市 2330 三天的融資融券餘額。"""
    fixtures = [
        ("TWSE_margin_20260916.json", date(2026, 9, 16), 19_500_000, 900_000),
        ("TWSE_margin_20260917.json", date(2026, 9, 17), 20_000_000, 1_000_000),
        ("TWSE_margin_20260918.json", date(2026, 9, 18), 20_200_000, 1_090_000),
    ]

    for filename, expected_date, expected_margin, expected_short in fixtures:
        with open(f"etl/tests/fixtures/{filename}") as f:
            payload = json.load(f)
        records = parse_twse_margin(payload, expected_date)
        record_2330 = [r for r in records if r.stock_id == "2330"][0]
        assert record_2330.margin_balance == expected_margin
        assert record_2330.short_balance == expected_short


def test_上市_2330_20260918_十三個欄位():
    """測試上市 2330 的完整欄位值。"""
    with open("etl/tests/fixtures/TWSE_margin_20260918.json") as f:
        payload = json.load(f)
    records = parse_twse_margin(payload, date(2026, 9, 18))
    record_2330 = [r for r in records if r.stock_id == "2330"][0]

    assert record_2330.margin_buy == 1_200_000
    assert record_2330.margin_sell == 900_000
    assert record_2330.margin_redeem == 100_000
    assert record_2330.margin_prev_balance == 20_000_000
    assert record_2330.margin_balance == 20_200_000
    assert record_2330.margin_limit == 100_000_000
    assert record_2330.short_buy == 50_000
    assert record_2330.short_sell == 150_000
    assert record_2330.short_redeem == 10_000
    assert record_2330.short_prev_balance == 1_000_000
    assert record_2330.short_balance == 1_090_000
    assert record_2330.short_limit == 100_000_000
    assert record_2330.offset_amount == 20_000


def test_限額為破折號時是_None():
    """測試限額欄為 '-' 時應為 None。"""
    with open("etl/tests/fixtures/TWSE_margin_20260918.json") as f:
        payload = json.load(f)
    records = parse_twse_margin(payload, date(2026, 9, 18))
    record_0050 = [r for r in records if r.stock_id == "0050"][0]
    assert record_0050.margin_limit is None
    assert record_0050.short_limit is None


def test_上櫃新版解析三筆與_3105_數值():
    """測試上櫃融資融券新版端點，應得到 3 筆。"""
    with open("etl/tests/fixtures/TPEx_margin_20260918.json") as f:
        payload = json.load(f)
    records = parse_tpex_margin(payload, date(2026, 9, 18))
    assert len(records) == 3
    record_3105 = [r for r in records if r.stock_id == "3105"][0]
    assert record_3105.margin_prev_balance == 3_000_000
    assert record_3105.margin_buy == 200_000
    assert record_3105.margin_sell == 100_000
    assert record_3105.margin_redeem == 0
    assert record_3105.margin_balance == 3_100_000
    assert record_3105.margin_limit == 100_000_000
    assert record_3105.short_prev_balance == 200_000
    assert record_3105.short_sell == 50_000
    assert record_3105.short_buy == 20_000
    assert record_3105.short_redeem == 0
    assert record_3105.short_balance == 230_000
    assert record_3105.short_limit == 100_000_000
    assert record_3105.offset_amount == 5_000
    assert record_3105.source == "TPEx"


def test_上櫃舊版備援與新版結果逐欄相同():
    """測試上櫃舊版與新版解析結果應相同。"""
    with open("etl/tests/fixtures/TPEx_margin_20260918.json") as f:
        new_payload = json.load(f)
    with open("etl/tests/fixtures/TPEx_margin_legacy_sample.json") as f:
        legacy_payload = json.load(f)

    new_records = parse_tpex_margin(new_payload, date(2026, 9, 18))
    legacy_records = parse_tpex_margin(legacy_payload, date(2026, 9, 18))

    new_3105 = [r for r in new_records if r.stock_id == "3105"][0]
    legacy_3105 = [r for r in legacy_records if r.stock_id == "3105"][0]

    # 逐欄比對
    assert new_3105.margin_prev_balance == legacy_3105.margin_prev_balance
    assert new_3105.margin_buy == legacy_3105.margin_buy
    assert new_3105.margin_sell == legacy_3105.margin_sell
    assert new_3105.margin_redeem == legacy_3105.margin_redeem
    assert new_3105.margin_balance == legacy_3105.margin_balance
    assert new_3105.margin_limit == legacy_3105.margin_limit
    assert new_3105.short_prev_balance == legacy_3105.short_prev_balance
    assert new_3105.short_sell == legacy_3105.short_sell
    assert new_3105.short_buy == legacy_3105.short_buy
    assert new_3105.short_redeem == legacy_3105.short_redeem
    assert new_3105.short_balance == legacy_3105.short_balance
    assert new_3105.short_limit == legacy_3105.short_limit
    assert new_3105.offset_amount == legacy_3105.offset_amount


def test_缺必要欄位拋_SourceFormatError():
    """測試缺少必要欄位時應拋 SourceFormatError。"""
    with open("etl/tests/fixtures/TWSE_margin_20260918.json") as f:
        payload = json.load(f)

    # 修改欄位名稱
    payload["tables"][1]["fields"] = [
        "股票代號", "股票名稱", "融資買進", "融資賣出", "現金償還",
        "融資前日餘額", "XXX", "融資限額",  # 將「融資今日餘額」改成 XXX
        "融券買進", "融券賣出", "現券償還", "融券前日餘額",
        "融券今日餘額", "融券限額", "資券互抵", "註記"
    ]

    with pytest.raises(SourceFormatError):
        parse_twse_margin(payload, date(2026, 9, 18))


def test_fetch_上櫃新版失敗會退回舊版(caplog):
    """測試上櫃新版端點失敗時自動退回舊版。"""
    def transport_callback(request):
        if "margin/balance" in str(request.url):
            # 新版返回 500 錯誤
            return httpx.Response(500)
        else:
            # 舊版返回成功
            with open("etl/tests/fixtures/TPEx_margin_legacy_sample.json") as f:
                legacy_payload = json.load(f)
            return httpx.Response(200, json=legacy_payload)

    transport = httpx.MockTransport(transport_callback)
    with httpx.Client(transport=transport) as client:
        payload = fetch_tpex_margin(date(2026, 9, 18), client)
        # 驗證返回的是舊版格式
        assert "aaData" in payload
        assert "fields" not in payload
        # 檢查 caplog 有 warning
        assert "改用舊版" in caplog.text


def test_上市信用交易統計那張表不會被誤選():
    """測試信用交易統計表不會被當作股票融資融券明細。"""
    with open("etl/tests/fixtures/TWSE_margin_20260918.json") as f:
        payload = json.load(f)
    records = parse_twse_margin(payload, date(2026, 9, 18))
    # 應該只有 4 筆（2330, 1101, 0050, 9999）
    assert len(records) == 4
    # 第一筆應該是 2330
    assert records[0].stock_id == "2330"
