"""價格 loader 測試。"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from twstock_db.tables import adj_factor, daily_price, index_daily, stock
from twstock_etl.loaders.price import (
    count_prices,
    index_trade_dates,
    upsert_adj_factors,
    upsert_daily_prices,
    upsert_index_daily,
)
from twstock_etl.models import AdjFactorRecord, IndexRecord, PriceRecord


def test_upsert_daily_prices_basic(clean_db):
    """測試基本日 K 寫入。"""
    # 先插入測試用個股
    with clean_db.begin() as conn:
        conn.execute(
            stock.insert().values([
                {"stock_id": "2330", "name": "台積電", "market": "TWSE"},
                {"stock_id": "3105", "name": "穩懋", "market": "TPEx"},
            ])
        )

    # 準備測試資料
    records = [
        PriceRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 16),
            open=Decimal("995.00"),
            high=Decimal("1005.00"),
            low=Decimal("990.00"),
            close=Decimal("1000.00"),
            change=Decimal("5.00"),
            volume=25000000,
            turnover=Decimal("25000000000"),
            transactions=30000,
            source="TWSE",
        ),
        PriceRecord(
            stock_id="3105",
            trade_date=date(2026, 9, 16),
            open=Decimal("350.00"),
            high=Decimal("353.00"),
            low=Decimal("348.00"),
            close=Decimal("350.00"),
            change=Decimal("0.00"),
            volume=2800000,
            turnover=Decimal("980000000"),
            transactions=2300,
            source="TPEx",
        ),
        PriceRecord(
            stock_id="9999",  # 不在 stock 表中
            trade_date=date(2026, 9, 16),
            open=Decimal("100.00"),
            high=Decimal("100.00"),
            low=Decimal("100.00"),
            close=Decimal("100.00"),
            change=None,
            volume=0,
            turnover=Decimal("0"),
            transactions=0,
            source="TWSE",
        ),
    ]

    # 寫入
    with clean_db.begin() as conn:
        result = upsert_daily_prices(conn, records)

    assert result.written == 2
    assert result.skipped_unknown == 1

    # 驗證 DB 內容
    with clean_db.begin() as conn:
        rows = conn.execute(select(daily_price)).fetchall()
    assert len(rows) == 2
    assert [r.stock_id for r in rows] == ["2330", "3105"]


def test_upsert_daily_prices_upsert(clean_db):
    """測試 upsert 覆蓋。"""
    with clean_db.begin() as conn:
        conn.execute(
            stock.insert().values({"stock_id": "2330", "name": "台積電", "market": "TWSE"})
        )

    records1 = [
        PriceRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 18),
            open=Decimal("996.00"),
            high=Decimal("1010.00"),
            low=Decimal("995.00"),
            close=Decimal("1008.00"),
            change=Decimal("13.00"),
            volume=30000000,
            turnover=Decimal("30000000000"),
            transactions=35000,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        result1 = upsert_daily_prices(conn, records1)

    assert result1.written == 1

    # 再次寫入相同日期，改動收盤價
    records2 = [
        PriceRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 18),
            open=Decimal("996.00"),
            high=Decimal("1010.00"),
            low=Decimal("995.00"),
            close=Decimal("1000.00"),  # 改動
            change=Decimal("5.00"),
            volume=30000000,
            turnover=Decimal("30000000000"),
            transactions=35000,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        result2 = upsert_daily_prices(conn, records2)

    assert result2.written == 1

    # 驗證資料已更新
    with clean_db.begin() as conn:
        row = conn.execute(
            select(daily_price).where(daily_price.c.stock_id == "2330")
        ).first()
    assert row.close == Decimal("1000.00")


def test_upsert_daily_prices_dedup(clean_db):
    """測試同一批內去重（保留最後一筆）。"""
    with clean_db.begin() as conn:
        conn.execute(
            stock.insert().values({"stock_id": "2330", "name": "台積電", "market": "TWSE"})
        )

    records = [
        PriceRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 18),
            open=Decimal("996.00"),
            high=Decimal("1010.00"),
            low=Decimal("995.00"),
            close=Decimal("1008.00"),  # 第一筆
            change=Decimal("13.00"),
            volume=30000000,
            turnover=Decimal("30000000000"),
            transactions=35000,
            source="TWSE",
        ),
        PriceRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 18),
            open=Decimal("996.00"),
            high=Decimal("1010.00"),
            low=Decimal("995.00"),
            close=Decimal("1000.00"),  # 第二筆，不同收盤價
            change=Decimal("5.00"),
            volume=25000000,
            turnover=Decimal("25000000000"),
            transactions=25000,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        result = upsert_daily_prices(conn, records)

    assert result.written == 1

    # 驗證保留的是最後一筆
    with clean_db.begin() as conn:
        row = conn.execute(
            select(daily_price).where(daily_price.c.stock_id == "2330")
        ).first()
    assert row.close == Decimal("1000.00")


def test_upsert_index_daily(clean_db):
    """測試指數日 K 寫入。"""
    records = [
        IndexRecord(
            index_id="TAIEX",
            trade_date=date(2026, 9, 16),
            open=Decimal("24500.00"),
            high=Decimal("24680.00"),
            low=Decimal("24450.00"),
            close=Decimal("24600.00"),
        ),
        IndexRecord(
            index_id="TAIEX",
            trade_date=date(2026, 9, 17),
            open=Decimal("24610.00"),
            high=Decimal("24700.00"),
            low=Decimal("24560.00"),
            close=Decimal("24650.00"),
        ),
        IndexRecord(
            index_id="TAIEX",
            trade_date=date(2026, 9, 18),
            open=Decimal("24660.00"),
            high=Decimal("24800.00"),
            low=Decimal("24640.00"),
            close=Decimal("24780.00"),
        ),
    ]

    with clean_db.begin() as conn:
        count = upsert_index_daily(conn, records)

    assert count == 3

    # 驗證 trade_dates
    with clean_db.begin() as conn:
        dates = index_trade_dates(conn, "TAIEX", 2026)

    assert len(dates) == 3
    assert date(2026, 9, 16) in dates
    assert date(2026, 9, 17) in dates
    assert date(2026, 9, 18) in dates


def test_upsert_adj_factors(clean_db):
    """測試除權息係數寫入。"""
    with clean_db.begin() as conn:
        conn.execute(
            stock.insert().values([
                {"stock_id": "2330", "name": "台積電", "market": "TWSE"},
                {"stock_id": "1101", "name": "台泥", "market": "TWSE"},
            ])
        )

    records = [
        AdjFactorRecord(
            stock_id="2330",
            ex_date=date(2026, 9, 17),
            factor=Decimal("0.99000000"),
            prev_close=Decimal("1000.00"),
            reference_price=Decimal("990.00"),
            kind="除息",
            source="TWSE",
        ),
        AdjFactorRecord(
            stock_id="1101",
            ex_date=date(2026, 9, 16),
            factor=Decimal("0.99447514"),
            prev_close=Decimal("36.20"),
            reference_price=Decimal("36.00"),
            kind="除息",
            source="TWSE",
        ),
        AdjFactorRecord(
            stock_id="9999",  # 不在 stock 表中
            ex_date=date(2026, 9, 18),
            factor=Decimal("0.99000000"),
            prev_close=Decimal("100.00"),
            reference_price=Decimal("99.00"),
            kind="除息",
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        result = upsert_adj_factors(conn, records)

    assert result.written == 2
    assert result.skipped_unknown == 1

    # 驗證 DB 內容
    with clean_db.begin() as conn:
        rows = conn.execute(select(adj_factor)).fetchall()
    assert len(rows) == 2


def test_count_prices(clean_db):
    """測試計算已寫入的日 K 筆數。"""
    with clean_db.begin() as conn:
        conn.execute(
            stock.insert().values([
                {"stock_id": "2330", "name": "台積電", "market": "TWSE"},
                {"stock_id": "3105", "name": "穩懋", "market": "TPEx"},
            ])
        )

    records_twse = [
        PriceRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 18),
            open=Decimal("996.00"),
            high=Decimal("1010.00"),
            low=Decimal("995.00"),
            close=Decimal("1008.00"),
            change=Decimal("13.00"),
            volume=30000000,
            turnover=Decimal("30000000000"),
            transactions=35000,
            source="TWSE",
        ),
    ]

    records_tpex = [
        PriceRecord(
            stock_id="3105",
            trade_date=date(2026, 9, 18),
            open=Decimal("349.00"),
            high=Decimal("349.00"),
            low=Decimal("349.00"),
            close=Decimal("349.00"),
            change=Decimal("-3.00"),
            volume=2800000,
            turnover=Decimal("980000000"),
            transactions=2300,
            source="TPEx",
        ),
    ]

    with clean_db.begin() as conn:
        upsert_daily_prices(conn, records_twse)
        upsert_daily_prices(conn, records_tpex)

    with clean_db.begin() as conn:
        twse_count = count_prices(conn, date(2026, 9, 18), "TWSE")
        tpex_count = count_prices(conn, date(2026, 9, 18), "TPEx")

    assert twse_count == 1
    assert tpex_count == 1
