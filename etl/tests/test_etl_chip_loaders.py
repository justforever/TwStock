"""籌碼 loaders 測試。"""

from datetime import date
from sqlalchemy import func, select

from twstock_db.tables import institutional_daily, margin_daily, foreign_holding
from twstock_etl.loaders.chip import (
    upsert_institutional,
    upsert_margin,
    upsert_sbl,
    upsert_foreign_holding,
)
from twstock_etl.loaders.price import PriceUpsertResult
from twstock_etl.models import (
    InstitutionalRecord,
    MarginRecord,
    SblRecord,
    ForeignHoldingRecord,
)


def test_upsert_institutional_insert(clean_db):
    """測試新增三大法人資料。"""
    records = [
        InstitutionalRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 21),
            foreign_buy=100,
            foreign_sell=50,
            foreign_net=50,
            trust_buy=200,
            trust_sell=100,
            trust_net=100,
            dealer_buy=300,
            dealer_sell=150,
            dealer_net=150,
            total_net=300,
            source="TWSE",
        ),
        InstitutionalRecord(
            stock_id="2454",
            trade_date=date(2026, 9, 21),
            foreign_buy=50,
            foreign_sell=25,
            foreign_net=25,
            trust_buy=100,
            trust_sell=50,
            trust_net=50,
            dealer_buy=150,
            dealer_sell=75,
            dealer_net=75,
            total_net=150,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        # 先插入股票
        from twstock_db.tables import stock as stock_table
        conn.execute(
            stock_table.insert().values([
                {"stock_id": "2330", "name": "台積電", "market": "TWSE", "industry": "半導體", "listed_date": date(1994, 9, 5), "is_etf": False, "isin_code": "TW0002330008", "cfi_code": "ESVUFR"},
                {"stock_id": "2454", "name": "聯發科", "market": "TWSE", "industry": "IC設計", "listed_date": date(1997, 9, 26), "is_etf": False, "isin_code": "TW0002454001", "cfi_code": "ESVUFR"},
            ])
        )

    with clean_db.begin() as conn:
        result = upsert_institutional(conn, records)

    assert result.written == 2
    assert result.skipped_unknown == 0

    with clean_db.begin() as conn:
        rows = conn.execute(select(func.count()).select_from(institutional_daily)).scalar()
    assert rows == 2


def test_upsert_institutional_idempotent(clean_db):
    """測試三大法人資料冪等性。"""
    records = [
        InstitutionalRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 21),
            foreign_buy=100,
            foreign_sell=50,
            foreign_net=50,
            trust_buy=200,
            trust_sell=100,
            trust_net=100,
            dealer_buy=300,
            dealer_sell=150,
            dealer_net=150,
            total_net=300,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        from twstock_db.tables import stock as stock_table
        conn.execute(
            stock_table.insert().values({
                "stock_id": "2330",
                "name": "台積電",
                "market": "TWSE",
                "industry": "半導體",
                "listed_date": date(1994, 9, 5),
                "is_etf": False,
                "isin_code": "TW0002330008",
                "cfi_code": "ESVUFR",
            })
        )

    with clean_db.begin() as conn:
        result1 = upsert_institutional(conn, records)

    with clean_db.begin() as conn:
        result2 = upsert_institutional(conn, records)

    assert result1.written == 1
    assert result2.written == 1

    with clean_db.begin() as conn:
        rows = conn.execute(select(func.count()).select_from(institutional_daily)).scalar()
    assert rows == 1


def test_upsert_institutional_skip_unknown(clean_db):
    """測試略過未知個股。"""
    records = [
        InstitutionalRecord(
            stock_id="9999",  # 不存在的代號
            trade_date=date(2026, 9, 21),
            foreign_buy=100,
            foreign_sell=50,
            foreign_net=50,
            trust_buy=200,
            trust_sell=100,
            trust_net=100,
            dealer_buy=300,
            dealer_sell=150,
            dealer_net=150,
            total_net=300,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        result = upsert_institutional(conn, records)

    assert result.written == 0
    assert result.skipped_unknown == 1


def test_upsert_margin_insert(clean_db):
    """測試新增融資融券資料。"""
    records = [
        MarginRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 21),
            margin_buy=1000,
            margin_sell=500,
            margin_redeem=100,
            margin_prev_balance=5000,
            margin_balance=5400,
            margin_limit=10000,
            short_buy=200,
            short_sell=100,
            short_redeem=20,
            short_prev_balance=1000,
            short_balance=1080,
            short_limit=2000,
            offset_amount=0,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        from twstock_db.tables import stock as stock_table
        conn.execute(
            stock_table.insert().values({
                "stock_id": "2330",
                "name": "台積電",
                "market": "TWSE",
                "industry": "半導體",
                "listed_date": date(1994, 9, 5),
                "is_etf": False,
                "isin_code": "TW0002330008",
                "cfi_code": "ESVUFR",
            })
        )

    with clean_db.begin() as conn:
        result = upsert_margin(conn, records)

    assert result.written == 1
    assert result.skipped_unknown == 0


def test_upsert_sbl_insert(clean_db):
    """測試新增借券資料。"""
    records = [
        SblRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 21),
            sbl_sell=500,
            sbl_balance=2000,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        from twstock_db.tables import stock as stock_table
        conn.execute(
            stock_table.insert().values({
                "stock_id": "2330",
                "name": "台積電",
                "market": "TWSE",
                "industry": "半導體",
                "listed_date": date(1994, 9, 5),
                "is_etf": False,
                "isin_code": "TW0002330008",
                "cfi_code": "ESVUFR",
            })
        )

    with clean_db.begin() as conn:
        result = upsert_sbl(conn, records)

    assert result.written == 1
    assert result.skipped_unknown == 0


def test_upsert_foreign_holding_insert(clean_db):
    """測試新增外資持股資料。"""
    records = [
        ForeignHoldingRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 21),
            issued_shares=1000000,
            holding_shares=200000,
            available_shares=180000,
            holding_ratio=0.20,
            available_ratio=0.18,
            limit_ratio=0.30,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        from twstock_db.tables import stock as stock_table
        conn.execute(
            stock_table.insert().values({
                "stock_id": "2330",
                "name": "台積電",
                "market": "TWSE",
                "industry": "半導體",
                "listed_date": date(1994, 9, 5),
                "is_etf": False,
                "isin_code": "TW0002330008",
                "cfi_code": "ESVUFR",
            })
        )

    with clean_db.begin() as conn:
        result = upsert_foreign_holding(conn, records)

    assert result.written == 1
    assert result.skipped_unknown == 0


def test_upsert_margin_then_sbl_isolation(clean_db):
    """測試 D-037：先 upsert_margin 再 upsert_sbl，margin_balance 不變。"""
    margin_records = [
        MarginRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 21),
            margin_buy=1000,
            margin_sell=500,
            margin_redeem=100,
            margin_prev_balance=5000,
            margin_balance=5400,
            margin_limit=10000,
            short_buy=200,
            short_sell=100,
            short_redeem=20,
            short_prev_balance=1000,
            short_balance=1080,
            short_limit=2000,
            offset_amount=0,
            source="TWSE",
        ),
    ]

    sbl_records = [
        SblRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 21),
            sbl_sell=500,
            sbl_balance=2000,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        from twstock_db.tables import stock as stock_table
        conn.execute(
            stock_table.insert().values({
                "stock_id": "2330",
                "name": "台積電",
                "market": "TWSE",
                "industry": "半導體",
                "listed_date": date(1994, 9, 5),
                "is_etf": False,
                "isin_code": "TW0002330008",
                "cfi_code": "ESVUFR",
            })
        )

    # 先寫入融資融券
    with clean_db.begin() as conn:
        margin_result = upsert_margin(conn, margin_records)
        assert margin_result.written == 1

    # 再寫入借券
    with clean_db.begin() as conn:
        sbl_result = upsert_sbl(conn, sbl_records)
        assert sbl_result.written == 1

    # 驗證兩筆資料都在，且欄位沒有互相覆蓋
    with clean_db.begin() as conn:
        row = conn.execute(
            select(margin_daily.c.margin_balance, margin_daily.c.sbl_balance).where(
                (margin_daily.c.stock_id == "2330")
                & (margin_daily.c.trade_date == date(2026, 9, 21))
            )
        ).first()

    assert row[0] == 5400  # margin_balance 未被覆蓋
    assert row[1] == 2000  # sbl_balance 已寫入


def test_upsert_sbl_then_margin_isolation(clean_db):
    """測試 D-037：先 upsert_sbl（空表）再 upsert_margin，sbl_balance 不變。"""
    sbl_records = [
        SblRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 21),
            sbl_sell=500,
            sbl_balance=2000,
            source="TWSE",
        ),
    ]

    margin_records = [
        MarginRecord(
            stock_id="2330",
            trade_date=date(2026, 9, 21),
            margin_buy=1000,
            margin_sell=500,
            margin_redeem=100,
            margin_prev_balance=5000,
            margin_balance=5400,
            margin_limit=10000,
            short_buy=200,
            short_sell=100,
            short_redeem=20,
            short_prev_balance=1000,
            short_balance=1080,
            short_limit=2000,
            offset_amount=0,
            source="TWSE",
        ),
    ]

    with clean_db.begin() as conn:
        from twstock_db.tables import stock as stock_table
        conn.execute(
            stock_table.insert().values({
                "stock_id": "2330",
                "name": "台積電",
                "market": "TWSE",
                "industry": "半導體",
                "listed_date": date(1994, 9, 5),
                "is_etf": False,
                "isin_code": "TW0002330008",
                "cfi_code": "ESVUFR",
            })
        )

    # 先寫入借券到空表
    with clean_db.begin() as conn:
        sbl_result = upsert_sbl(conn, sbl_records)
        assert sbl_result.written == 1

    # 再寫入融資融券
    with clean_db.begin() as conn:
        margin_result = upsert_margin(conn, margin_records)
        assert margin_result.written == 1

    # 驗證兩筆資料都在，且欄位沒有互相覆蓋
    with clean_db.begin() as conn:
        row = conn.execute(
            select(margin_daily.c.sbl_balance, margin_daily.c.margin_balance).where(
                (margin_daily.c.stock_id == "2330")
                & (margin_daily.c.trade_date == date(2026, 9, 21))
            )
        ).first()

    assert row[0] == 2000  # sbl_balance 未被覆蓋
    assert row[1] == 5400  # margin_balance 已寫入
