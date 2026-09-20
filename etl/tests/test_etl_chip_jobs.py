"""籌碼 jobs 測試。"""

from datetime import date
import json
from pathlib import Path
from sqlalchemy import func, select

from twstock_db.tables import institutional_daily, etl_job_log, stock as stock_table
from twstock_etl.jobs import load_chip_daily, ChipJobResult
from twstock_etl.loaders.calendar import upsert_calendar
from twstock_etl.models import CalendarDay


def test_load_chip_institutional_twse(clean_db):
    """測試載入上市三大法人籌碼。"""
    # 先建立股票與交易日曆
    with clean_db.begin() as conn:
        conn.execute(
            stock_table.insert().values([
                {
                    "stock_id": "2330",
                    "name": "台積電",
                    "market": "TWSE",
                    "industry": "半導體",
                    "listed_date": date(1994, 9, 5),
                    "is_etf": False,
                    "isin_code": "TW0002330008",
                    "cfi_code": "ESVUFR",
                },
                {
                    "stock_id": "2454",
                    "name": "聯發科",
                    "market": "TWSE",
                    "industry": "IC設計",
                    "listed_date": date(1997, 9, 26),
                    "is_etf": False,
                    "isin_code": "TW0002454001",
                    "cfi_code": "ESVUFR",
                },
            ])
        )
        upsert_calendar(conn, [CalendarDay(date(2026, 9, 18), True, None)])

    # 讀取實際 fixture
    fixture_path = Path(__file__).parent / "fixtures" / "TWSE_institutional_20260918.json"
    with open(fixture_path) as f:
        payload = json.load(f)

    result = load_chip_daily(
        clean_db,
        "institutional",
        "TWSE",
        date(2026, 9, 18),
        payload=payload,
        check_calendar=False,
    )

    assert isinstance(result, ChipJobResult)
    assert result.kind == "institutional"
    assert result.market == "TWSE"
    assert result.rows > 0
    assert result.skip_reason is None

    # 驗證 etl_job_log 有寫入
    with clean_db.begin() as conn:
        log_rows = conn.execute(
            select(func.count()).select_from(etl_job_log).where(
                etl_job_log.c.job_name == "institutional_twse"
            )
        ).scalar()
    assert log_rows == 1


def test_load_chip_institutional_tpex(clean_db):
    """測試載入上櫃三大法人籌碼。"""
    # 先建立股票與交易日曆
    with clean_db.begin() as conn:
        conn.execute(
            stock_table.insert().values([
                {
                    "stock_id": "1101",
                    "name": "台泥",
                    "market": "TPEx",
                    "industry": "水泥",
                    "listed_date": date(1962, 2, 9),
                    "is_etf": False,
                    "isin_code": "TW0001101007",
                    "cfi_code": "ESVUFR",
                },
                {
                    "stock_id": "3105",
                    "name": "穩懋",
                    "market": "TPEx",
                    "industry": "半導體",
                    "listed_date": date(1998, 8, 10),
                    "is_etf": False,
                    "isin_code": "TW0003105006",
                    "cfi_code": "ESVUFR",
                },
                {
                    "stock_id": "8069",
                    "name": "元成",
                    "market": "TPEx",
                    "industry": "電子零件",
                    "listed_date": date(2018, 7, 12),
                    "is_etf": False,
                    "isin_code": "TW0008069005",
                    "cfi_code": "ESVUFR",
                },
            ])
        )
        upsert_calendar(conn, [CalendarDay(date(2026, 9, 18), True, None)])

    # 讀取實際 fixture
    fixture_path = Path(__file__).parent / "fixtures" / "TPEx_institutional_20260918.json"
    with open(fixture_path) as f:
        payload = json.load(f)

    result = load_chip_daily(
        clean_db,
        "institutional",
        "TPEx",
        date(2026, 9, 18),
        payload=payload,
        check_calendar=False,
    )

    assert result.kind == "institutional"
    assert result.market == "TPEx"
    assert result.rows > 0
    assert result.skip_reason is None

    # 驗證 etl_job_log 有寫入
    with clean_db.begin() as conn:
        log_rows = conn.execute(
            select(func.count()).select_from(etl_job_log).where(
                etl_job_log.c.job_name == "institutional_tpex"
            )
        ).scalar()
    assert log_rows == 1


def test_load_chip_non_trading_day_skip(clean_db):
    """測試非開市日被略過。"""
    with clean_db.begin() as conn:
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
        # 建立 2026-09-18 為休市日
        upsert_calendar(conn, [CalendarDay(date(2026, 9, 18), False, "週末")])

    result = load_chip_daily(
        clean_db,
        "institutional",
        "TWSE",
        date(2026, 9, 18),
        check_calendar=True,
    )

    # 應該因為非開市日而被略過
    assert result.skip_reason == "非開市日"
    assert result.rows == 0

    # 但 etl_job_log 仍會有一列記錄（記錄此次 skip）
    with clean_db.begin() as conn:
        log_rows = conn.execute(
            select(etl_job_log.c.status).where(
                etl_job_log.c.job_name == "institutional_twse"
            )
        ).scalar()
    # skip 時 status 應為 "skipped"
    assert log_rows == "skipped"


def test_load_chip_invalid_combo_raises(clean_db):
    """測試無效的 kind/market 組合會拋 ValueError，且不寫 etl_job_log。"""
    # sbl 在 TPEx 不存在
    try:
        load_chip_daily(
            clean_db,
            "sbl",
            "TPEx",
            date(2026, 9, 18),
        )
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "沒有這個籌碼來源" in str(e)

    # ValueError 拋出前就離開 job_run，所以 etl_job_log 沒有新增列
    with clean_db.begin() as conn:
        log_rows = conn.execute(select(func.count()).select_from(etl_job_log)).scalar()
    assert log_rows == 0


def test_load_chip_all_kinds_have_job_names(clean_db):
    """測試所有四種籌碼 kind 都能通過 get_chip_source。"""
    from twstock_etl.chip_sources import CHIP_SOURCES

    # 檢查所有四種 kind 都有至少一個來源
    kinds = set(k for k, m in CHIP_SOURCES.keys())
    expected_kinds = {"institutional", "margin", "sbl", "foreign"}
    assert kinds == expected_kinds

    # 檢查所有來源都有 job_name
    expected_job_names = {
        ("institutional", "TWSE"): "institutional_twse",
        ("institutional", "TPEx"): "institutional_tpex",
        ("margin", "TWSE"): "margin_twse",
        ("margin", "TPEx"): "margin_tpex",
        ("sbl", "TWSE"): "sbl_twse",
        ("foreign", "TWSE"): "foreign_holding_twse",
    }

    for key, source in CHIP_SOURCES.items():
        assert source.job_name is not None
        assert source.job_name == expected_job_names[key]
