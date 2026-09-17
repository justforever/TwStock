"""ETL loaders 測試。"""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from twstock_db.engine import get_engine
from twstock_db.tables import stock, trading_calendar
from twstock_etl.errors import SourceFormatError
from twstock_etl.jobs import refresh_stock_list, refresh_trading_calendar
from twstock_etl.loaders.calendar import upsert_calendar
from twstock_etl.loaders.stock import deactivate_missing, upsert_stocks
from twstock_etl.models import CalendarDay, StockRecord
from twstock_etl.sources.isin import parse_isin_html
from twstock_etl.sources.twse_holiday import build_calendar, parse_holiday_schedule
import json


def _load_fixture(filename: str) -> str:
    """讀取 fixture 檔案。"""
    path = Path(__file__).parent / "fixtures" / filename
    return path.read_text(encoding="utf-8")


def test_upsert_stocks_insert(clean_db):
    """測試新增個股。"""
    html = _load_fixture("isin_twse_strmode2.html")
    records = parse_isin_html(html, "TWSE")

    with clean_db.begin() as conn:
        count = upsert_stocks(conn, records)

    assert count == 9
    with clean_db.begin() as conn:
        rows = conn.execute(select(func.count()).select_from(stock)).scalar()
    assert rows == 9


def test_upsert_stocks_idempotent(clean_db):
    """測試冪等性：同一批寫兩次。"""
    html = _load_fixture("isin_twse_strmode2.html")
    records = parse_isin_html(html, "TWSE")

    with clean_db.begin() as conn:
        count1 = upsert_stocks(conn, records)

    with clean_db.begin() as conn:
        count2 = upsert_stocks(conn, records)

    assert count1 == 9
    assert count2 == 9

    with clean_db.begin() as conn:
        rows = conn.execute(select(func.count()).select_from(stock)).scalar()
    assert rows == 9


def test_upsert_stocks_updates_fields(clean_db):
    """測試更新欄位。"""
    html = _load_fixture("isin_twse_strmode2.html")
    records = parse_isin_html(html, "TWSE")

    with clean_db.begin() as conn:
        upsert_stocks(conn, records)

        # 查詢原始的 2330
        row1 = conn.execute(
            select(stock).where(stock.c.stock_id == "2330")
        ).first()
        original_updated_at = row1.updated_at

    # 修改 2330 名稱
    modified_record = StockRecord(
        stock_id="2330",
        name="台積",
        market="TWSE",
        industry="半導體業",
        listed_date=date(1994, 9, 5),
        is_etf=False,
        isin_code="TW0002330008",
        cfi_code="ESVUFR",
    )

    with clean_db.begin() as conn:
        upsert_stocks(conn, [modified_record])

        # 查詢更新後的 2330
        row2 = conn.execute(
            select(stock).where(stock.c.stock_id == "2330")
        ).first()

    assert row2.name == "台積"
    assert row2.updated_at >= original_updated_at


def test_upsert_reactivates(clean_db):
    """測試重新啟用停用的個股。"""
    html = _load_fixture("isin_twse_strmode2.html")
    records = parse_isin_html(html, "TWSE")

    with clean_db.begin() as conn:
        upsert_stocks(conn, records)

        # 手動停用 2330
        conn.execute(
            stock.update()
            .where(stock.c.stock_id == "2330")
            .values(is_active=False)
        )

    # 再次 upsert，應該重新啟用
    with clean_db.begin() as conn:
        upsert_stocks(conn, records)

        row = conn.execute(
            select(stock).where(stock.c.stock_id == "2330")
        ).first()

    assert row.is_active is True


def test_deactivate_missing(clean_db):
    """測試停用缺漏的個股。"""
    twse_html = _load_fixture("isin_twse_strmode2.html")
    tpex_html = _load_fixture("isin_tpex_strmode4.html")
    twse_records = parse_isin_html(twse_html, "TWSE")
    tpex_records = parse_isin_html(tpex_html, "TPEx")

    with clean_db.begin() as conn:
        upsert_stocks(conn, twse_records)
        upsert_stocks(conn, tpex_records)

    # 停用 TWSE 中除了 2330 外的所有個股
    with clean_db.begin() as conn:
        deactivated = deactivate_missing(conn, "TWSE", {"2330"})

    assert deactivated == 8  # 共 9 筆，保留 1 筆，停用 8 筆

    # 驗證 TPEx 不受影響
    with clean_db.begin() as conn:
        tpex_active_count = conn.execute(
            select(func.count()).select_from(stock).where(
                (stock.c.market == "TPEx") & stock.c.is_active
            )
        ).scalar()
    assert tpex_active_count == 8


def test_deactivate_missing_empty_raises(clean_db):
    """測試 keep_ids 為空時拋錯。"""
    with clean_db.begin() as conn:
        with pytest.raises(ValueError, match="keep_ids"):
            deactivate_missing(conn, "TWSE", set())


def test_upsert_calendar_idempotent(clean_db):
    """測試日曆冪等性。"""
    json_str = _load_fixture("twse_holiday_schedule_2026.json")
    payload = json.loads(json_str)
    holidays = parse_holiday_schedule(payload)
    days = build_calendar(2026, holidays)

    with clean_db.begin() as conn:
        count1 = upsert_calendar(conn, days)

    with clean_db.begin() as conn:
        count2 = upsert_calendar(conn, days)

    assert count1 == 365
    assert count2 == 365

    # 驗證開市日數
    with clean_db.begin() as conn:
        open_count = conn.execute(
            select(func.count()).select_from(trading_calendar).where(
                trading_calendar.c.is_open
            )
        ).scalar()
    assert open_count == 250


def test_refresh_stock_list_with_html(clean_db):
    """測試 refresh_stock_list 帶 HTML。"""
    html = _load_fixture("isin_tpex_strmode4.html")

    result = refresh_stock_list(clean_db, "TPEx", html=html)

    assert result.market == "TPEx"
    assert result.records == 8
    assert result.deactivated == 0


def test_refresh_stock_list_deactivate_guard(clean_db):
    """測試停用時的筆數保護。"""
    html = _load_fixture("isin_twse_strmode2.html")

    # 筆數少於 500，不應該停用
    with pytest.raises(SourceFormatError, match="少於 500"):
        refresh_stock_list(clean_db, "TWSE", html=html, deactivate=True)

    # 驗證沒有寫入 DB
    with clean_db.begin() as conn:
        count = conn.execute(select(func.count()).select_from(stock)).scalar()
    assert count == 0
