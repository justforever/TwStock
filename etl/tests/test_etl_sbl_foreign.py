"""借券賣出與外資持股 parser 測試。"""

import json
from datetime import date
from decimal import Decimal

import pytest

from twstock_etl.errors import SourceFormatError
from twstock_etl.sources.twse_sbl import parse_twse_sbl
from twstock_etl.sources.twse_foreign import parse_twse_foreign_holding


def test_借券解析三筆與_2330_數值():
    """測試借券賣出解析 fixture，應得到 3 筆。"""
    with open("etl/tests/fixtures/TWSE_sbl_20260918.json") as f:
        payload = json.load(f)
    records = parse_twse_sbl(payload, date(2026, 9, 18))
    assert len(records) == 3
    record_2330 = [r for r in records if r.stock_id == "2330"][0]
    assert record_2330.sbl_sell == 300_000
    assert record_2330.sbl_balance == 4_500_000
    assert record_2330.source == "TWSE"


def test_借券不做張轉股():
    """測試借券單位應該是股，不乘以 1000。"""
    with open("etl/tests/fixtures/TWSE_sbl_20260918.json") as f:
        payload = json.load(f)
    records = parse_twse_sbl(payload, date(2026, 9, 18))
    record_1101 = [r for r in records if r.stock_id == "1101"][0]
    # 原值是 105,000 股，不是 105,000,000
    assert record_1101.sbl_balance == 105_000


def test_外資持股_2330_六個欄位():
    """測試外資持股解析 fixture 的 2330 欄位值。"""
    with open("etl/tests/fixtures/TWSE_foreign_20260918.json") as f:
        payload = json.load(f)
    records = parse_twse_foreign_holding(payload, date(2026, 9, 18))
    record_2330 = [r for r in records if r.stock_id == "2330"][0]

    assert record_2330.issued_shares == 25_930_380_458
    assert record_2330.available_shares == 7_779_114_138
    assert record_2330.holding_shares == 18_151_266_320
    assert record_2330.available_ratio == Decimal("30.0000")
    assert record_2330.holding_ratio == Decimal("70.0000")
    assert record_2330.limit_ratio == Decimal("100.0000")


def test_外資持股缺上限比率欄也能解析():
    """測試缺少上限比率欄時應能解析，該欄為 None。"""
    with open("etl/tests/fixtures/TWSE_foreign_20260918.json") as f:
        payload = json.load(f)

    # 刪掉上限比率欄
    fields = payload["fields"]
    fields.remove("法令投資上限比率")
    for row in payload["data"]:
        row.pop()  # 刪掉最後一個值

    records = parse_twse_foreign_holding(payload, date(2026, 9, 18))
    record_2330 = [r for r in records if r.stock_id == "2330"][0]
    assert record_2330.limit_ratio is None
    # 其他欄位應該正常
    assert record_2330.holding_shares == 18_151_266_320
    assert record_2330.holding_ratio == Decimal("70.0000")


def test_兩者空表都拋_SourceFormatError():
    """測試空表應拋 SourceFormatError。"""
    with open("etl/tests/fixtures/TWSE_sbl_20260918.json") as f:
        sbl_payload = json.load(f)
    sbl_payload["data"] = []

    with pytest.raises(SourceFormatError):
        parse_twse_sbl(sbl_payload, date(2026, 9, 18))

    with open("etl/tests/fixtures/TWSE_foreign_20260918.json") as f:
        foreign_payload = json.load(f)
    foreign_payload["data"] = []

    with pytest.raises(SourceFormatError):
        parse_twse_foreign_holding(foreign_payload, date(2026, 9, 18))
