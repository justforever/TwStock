"""ETL 價格工作函式測試。"""

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine

from twstock_etl.jobs import (
    load_adj_factors,
    load_daily_price,
    load_index_month,
    rebuild_calendar_from_index,
)
from twstock_etl.loaders.calendar import upsert_calendar
from twstock_etl.models import CalendarDay, StockRecord


@pytest.fixture
def setup_db(clean_db):
    """準備測試用資料庫。"""
    engine = clean_db

    # 插入測試個股
    from twstock_etl.loaders.stock import upsert_stocks

    with engine.begin() as conn:
        stocks = [
            StockRecord("1101", "台泥", "TWSE", None, date(2012, 1, 1), False, "", ""),
            StockRecord("2317", "鴻海", "TWSE", None, date(2015, 1, 1), False, "", ""),
            StockRecord("2330", "台積電", "TWSE", None, date(1994, 9, 5), False, "", ""),
            StockRecord("2834", "臺企銀", "TWSE", None, date(2005, 1, 1), False, "", ""),
            StockRecord("0050", "元大台灣50", "TWSE", True, date(2003, 6, 30), False, "", ""),
            StockRecord("3105", "穩懋", "TPEx", None, date(2010, 1, 1), False, "", ""),
            StockRecord("8069", "元太", "TPEx", None, date(2014, 6, 1), False, "", ""),
            StockRecord("006201", "元大富櫃50", "TPEx", True, date(2018, 7, 1), False, "", ""),
        ]

        for stock in stocks:
            upsert_stocks(conn, [stock])

        # 插入交易日曆
        days = [
            CalendarDay(date(2026, 9, 16), True, None),
            CalendarDay(date(2026, 9, 17), True, None),
            CalendarDay(date(2026, 9, 18), True, None),
            CalendarDay(date(2026, 9, 19), False, None),
        ]
        upsert_calendar(conn, days)

    return engine


def test_load_daily_price_twse(setup_db):
    """測試上市日成交載入。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/TWSE_price_20260918.json")
    
    with open(fixture_path) as f:
        payload = json.load(f)
    
    result = load_daily_price(
        engine, "TWSE", date(2026, 9, 18), payload=payload, check_calendar=False
    )
    
    # 2882 不在 stock 表，2834 無成交，應該只有 4 筆（1101、2317、2330、0050）
    assert result.rows == 4
    assert result.skipped_unknown == 1


def test_load_daily_price_skip_when_done(setup_db):
    """測試已完成時跳過。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/TWSE_price_20260918.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    # 第一次正常執行
    result1 = load_daily_price(
        engine, "TWSE", date(2026, 9, 18), payload=payload, check_calendar=False
    )
    assert result1.rows == 4

    # 第二次應該跳過
    result2 = load_daily_price(
        engine, "TWSE", date(2026, 9, 18), payload=payload, check_calendar=False
    )
    assert result2.skip_reason == "已完成，略過"
    assert result2.rows == 0


def test_load_daily_price_skip_non_trading_day(setup_db):
    """測試非開市日跳過。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/TWSE_price_20260918.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    # 2026-09-19 是休市日，應該跳過
    result = load_daily_price(
        engine, "TWSE", date(2026, 9, 19), payload=payload, check_calendar=True
    )
    assert result.skip_reason == "非開市日"
    assert result.rows == 0


def test_load_daily_price_force(setup_db):
    """測試日成交強制重抓。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/TWSE_price_20260918.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    # 第一次正常執行
    result1 = load_daily_price(
        engine, "TWSE", date(2026, 9, 18), payload=payload, check_calendar=False
    )
    assert result1.rows == 4

    # 第二次用 force=True 應該重抓
    result2 = load_daily_price(
        engine, "TWSE", date(2026, 9, 18), payload=payload, check_calendar=False, force=True
    )
    assert result2.rows == 4
    assert result2.skip_reason is None


def test_load_index_month(setup_db):
    """測試指數月份載入。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/TAIEX_index_202609.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    result = load_index_month(engine, 2026, 9, payload=payload)
    assert result.rows == 3
    assert result.skip_reason is None


def test_load_index_month_skip_when_done(setup_db):
    """測試指數月份已完成時跳過。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/TAIEX_index_202609.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    # 第一次正常執行（當月會自動執行，不 skip）
    result1 = load_index_month(engine, 2026, 9, payload=payload)
    assert result1.rows == 3
    assert result1.skip_reason is None

    # 第二次應該也會執行（因為是當月，當月一律不 skip）
    result2 = load_index_month(engine, 2026, 9, payload=payload)
    assert result2.rows == 3
    assert result2.skip_reason is None


def test_load_index_month_force(setup_db):
    """測試指數月份強制重抓。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/TAIEX_index_202609.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    # 第一次正常執行（當月）
    result1 = load_index_month(engine, 2026, 9, payload=payload)
    assert result1.rows == 3

    # 第二次用 force=True 應該重抓（即使已完成也會重抓，但因為是當月本來就會執行）
    result2 = load_index_month(engine, 2026, 9, payload=payload, force=True)
    assert result2.rows == 3
    assert result2.skip_reason is None


def test_load_adj_factors(setup_db):
    """測試除權除息載入。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/exright_20260901_20260930.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    result = load_adj_factors(engine, date(2026, 9, 1), date(2026, 9, 30), payload=payload)
    # 應該有 2 筆（2330、1101），2317 因為前收盤價為 0 被跳過
    assert result.rows == 2
    assert result.skip_reason is None


def test_load_adj_factors_skip_when_done(setup_db):
    """測試除權息已完成時跳過。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/exright_20260901_20260930.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    # 第一次正常執行
    result1 = load_adj_factors(engine, date(2026, 9, 1), date(2026, 9, 30), payload=payload)
    assert result1.rows == 2

    # 第二次應該跳過
    result2 = load_adj_factors(engine, date(2026, 9, 1), date(2026, 9, 30), payload=payload)
    assert result2.skip_reason == "已完成，略過"
    assert result2.rows == 0


def test_load_adj_factors_force(setup_db):
    """測試除權息強制重抓。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/exright_20260901_20260930.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    # 第一次正常執行
    result1 = load_adj_factors(engine, date(2026, 9, 1), date(2026, 9, 30), payload=payload)
    assert result1.rows == 2

    # 第二次用 force=True 應該重抓
    result2 = load_adj_factors(engine, date(2026, 9, 1), date(2026, 9, 30), payload=payload, force=True)
    assert result2.rows == 2
    assert result2.skip_reason is None


def test_load_adj_factors_interval_too_long(setup_db):
    """測試區間過長檢查。"""
    engine = setup_db
    
    with pytest.raises(ValueError):
        load_adj_factors(engine, date(2026, 1, 1), date(2026, 12, 31))


def test_rebuild_calendar_from_index(setup_db):
    """測試從指數反推日曆。"""
    engine = setup_db
    
    # 準備指數資料（只有 3 天，不足以反推）
    fixture_path = Path("etl/tests/fixtures/TAIEX_index_202609.json")
    
    with open(fixture_path) as f:
        payload = json.load(f)
    
    load_index_month(engine, 2026, 9, payload=payload)
    
    # 嘗試反推應該失敗
    with pytest.raises(Exception):  # SourceFormatError
        rebuild_calendar_from_index(engine, 2026)


def test_load_price_tpex(setup_db):
    """測試上櫃日成交載入。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/TPEx_price_20260918.json")
    
    with open(fixture_path) as f:
        payload = json.load(f)
    
    result = load_daily_price(
        engine, "TPEx", date(2026, 9, 18), payload=payload, check_calendar=False
    )
    
    # 5347 無成交，1258 不在 stock 表，應該只有 3 筆（3105、8069、006201）
    assert result.rows == 3
    assert result.skipped_unknown == 1
