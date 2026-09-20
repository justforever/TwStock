"""集保股權分散 parser 測試。"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from twstock_etl.errors import SourceFormatError
from twstock_etl.sources.tdcc import parse_tdcc_shareholding


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_解析_fixture_得到_26_筆():
    """測試 fixture 解析結果為 26 筆。"""
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")
    records = parse_tdcc_shareholding(text)
    assert len(records) == 26


def test_2330_level_15_的數值():
    """測試 2330 level 15 的數值。"""
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")
    records = parse_tdcc_shareholding(text)

    record = next(r for r in records if r.stock_id == "2330" and r.level == 15)
    assert record.holders == 1500
    assert record.shares == 500_000_000
    assert record.ratio == Decimal("50.0000")
    assert record.week_date == date(2026, 9, 18)


def test_千分位被清掉():
    """測試 2330 level 16 的千分位被清掉。"""
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")
    records = parse_tdcc_shareholding(text)

    record = next(r for r in records if r.stock_id == "2330" and r.level == 16)
    assert record.holders == 1_000_000
    assert record.shares == 1_000_000_000


def test_未知代號也會被解析出來():
    """測試未知代號 9999 有 2 筆（過濾是 loader 的事）。"""
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")
    records = parse_tdcc_shareholding(text)

    records_9999 = [r for r in records if r.stock_id == "9999"]
    assert len(records_9999) == 2


def test_表頭缺欄位拋_SourceFormatError():
    """測試表頭缺欄位拋 SourceFormatError。"""
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")
    text = text.replace("持股分級", "XX")

    with pytest.raises(SourceFormatError):
        parse_tdcc_shareholding(text)


def test_只有表頭拋_SourceFormatError():
    """測試只有表頭拋 SourceFormatError。"""
    text = "資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%"

    with pytest.raises(SourceFormatError):
        parse_tdcc_shareholding(text)


def test_級距_0_與_18_被略過():
    """測試級距 0 與 18 被略過。"""
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")
    # 只保留表頭與一行有效資料
    lines = text.split("\n")
    header = lines[0]
    valid_data = lines[1]  # 2330, level 1

    # 加上 level=0 與 level=18 的行
    text_with_invalid = header + "\n"
    text_with_invalid += "20260918,3333,0,100,1000,0.10\n"
    text_with_invalid += "20260918,3333,18,100,1000,0.10\n"
    text_with_invalid += valid_data

    records = parse_tdcc_shareholding(text_with_invalid)
    assert len(records) == 1  # 只有有效的 level 1 那一筆


def test_日期兩種寫法都認得():
    """測試日期 20260918 與 2026/09/18 都解析成 date(2026, 9, 18)。"""
    text_yyyymmdd = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(
        encoding="utf-8"
    )
    text_yyyy_mm_dd = text_yyyymmdd.replace("20260918", "2026/09/18")

    records_yyyymmdd = parse_tdcc_shareholding(text_yyyymmdd)
    records_yyyy_mm_dd = parse_tdcc_shareholding(text_yyyy_mm_dd)

    assert all(r.week_date == date(2026, 9, 18) for r in records_yyyymmdd)
    assert all(r.week_date == date(2026, 9, 18) for r in records_yyyy_mm_dd)
