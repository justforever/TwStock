"""集保股權分散 loader 與 job 測試。"""

import time
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from twstock_db.tables import etl_job_log, shareholding_dist
from twstock_etl.errors import SourceFormatError
from twstock_etl.jobs import load_shareholding
from twstock_etl.loaders.shareholding import upsert_shareholding
from twstock_etl.sources.tdcc import parse_tdcc_shareholding


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_upsert_寫入_24_筆_未知代號_1(clean_db):
    """測試 upsert 寫入 24 筆、未知代號 1。"""
    # 先塞入已知個股
    from twstock_etl.loaders.stock import upsert_stocks
    from twstock_etl.models import StockRecord

    with clean_db.begin() as conn:
        stock_records = [
            StockRecord(
                stock_id="2330",
                name="台積電",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
            StockRecord(
                stock_id="1101",
                name="台泥",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
            StockRecord(
                stock_id="3105",
                name="穩懋",
                market="TPEx",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
        ]
        upsert_stocks(conn, stock_records)

    # 讀取並解析 fixture
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")
    records = parse_tdcc_shareholding(text)

    # upsert
    with clean_db.begin() as conn:
        result = upsert_shareholding(conn, records)

    assert result.written == 24
    assert result.skipped_unknown == 1


def test_upsert_重載時_updated_at_會更新(clean_db):
    """重複 upsert 同一批集保資料時，updated_at 必須被更新（U-15）。"""
    from twstock_etl.loaders.stock import upsert_stocks
    from twstock_etl.models import StockRecord

    with clean_db.begin() as conn:
        upsert_stocks(
            conn,
            [
                StockRecord(
                    stock_id="2330",
                    name="台積電",
                    market="TWSE",
                    industry=None,
                    listed_date=None,
                    is_etf=False,
                    isin_code=None,
                    cfi_code=None,
                )
            ],
        )

    text_csv = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")
    records = [r for r in parse_tdcc_shareholding(text_csv) if r.stock_id == "2330"]
    assert records, "fixture 應該有 2330 的資料"

    with clean_db.begin() as conn:
        upsert_shareholding(conn, records)
        first = conn.execute(
            select(shareholding_dist.c.updated_at)
            .where(shareholding_dist.c.stock_id == "2330")
            .order_by(shareholding_dist.c.level)
            .limit(1)
        ).scalar_one()

    time.sleep(0.01)

    with clean_db.begin() as conn:
        upsert_shareholding(conn, records)
        second = conn.execute(
            select(shareholding_dist.c.updated_at)
            .where(shareholding_dist.c.stock_id == "2330")
            .order_by(shareholding_dist.c.level)
            .limit(1)
        ).scalar_one()

    assert second > first


def test_重跑同一份資料不會變成_48_筆(clean_db):
    """測試重跑同一份資料不會重複寫入。"""
    # 先塞入已知個股
    from twstock_etl.loaders.stock import upsert_stocks
    from twstock_etl.models import StockRecord

    with clean_db.begin() as conn:
        stock_records = [
            StockRecord(
                stock_id="2330",
                name="台積電",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
            StockRecord(
                stock_id="1101",
                name="台泥",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
            StockRecord(
                stock_id="3105",
                name="穩懋",
                market="TPEx",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
        ]
        upsert_stocks(conn, stock_records)

    # 讀取並解析 fixture
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")
    records = parse_tdcc_shareholding(text)

    # 第一次 upsert
    with clean_db.begin() as conn:
        upsert_shareholding(conn, records)

    # 第二次 upsert
    with clean_db.begin() as conn:
        result = upsert_shareholding(conn, records)

    # 驗證資料數
    with clean_db.begin() as conn:
        stmt = select(shareholding_dist)
        result = conn.execute(stmt)
        rows = result.fetchall()

    assert len(rows) == 24


def test_load_shareholding_寫_etl_job_log_的_target_date(clean_db):
    """測試 load_shareholding 寫入 etl_job_log 的 target_date。"""
    # 先塞入已知個股
    from twstock_etl.loaders.stock import upsert_stocks
    from twstock_etl.models import StockRecord

    with clean_db.begin() as conn:
        stock_records = [
            StockRecord(
                stock_id="2330",
                name="台積電",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
            StockRecord(
                stock_id="1101",
                name="台泥",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
            StockRecord(
                stock_id="3105",
                name="穩懋",
                market="TPEx",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
        ]
        upsert_stocks(conn, stock_records)

    # 讀取 fixture
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")

    # 呼叫 load_shareholding
    result = load_shareholding(clean_db, csv_text=text)

    # 驗證結果
    assert result.week_date == date(2026, 9, 18)
    assert result.rows == 24
    assert result.skip_reason is None

    # 驗證 etl_job_log
    with clean_db.begin() as conn:
        stmt = select(etl_job_log).where(etl_job_log.c.job_name == "shareholding_tdcc")
        result = conn.execute(stmt).first()

    assert result is not None
    assert result.status == "success"
    assert result.target_date == date(2026, 9, 18)
    assert result.rows == 24


def test_第二次呼叫會_skip(clean_db):
    """測試第二次呼叫會被 skip。"""
    # 先塞入已知個股
    from twstock_etl.loaders.stock import upsert_stocks
    from twstock_etl.models import StockRecord

    with clean_db.begin() as conn:
        stock_records = [
            StockRecord(
                stock_id="2330",
                name="台積電",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
            StockRecord(
                stock_id="1101",
                name="台泥",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
            StockRecord(
                stock_id="3105",
                name="穩懋",
                market="TPEx",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
        ]
        upsert_stocks(conn, stock_records)

    # 讀取 fixture
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")

    # 第一次呼叫
    load_shareholding(clean_db, csv_text=text)

    # 第二次呼叫
    result = load_shareholding(clean_db, csv_text=text)

    # 驗證結果
    assert result.rows == 0
    assert result.skip_reason == "已完成，略過"

    # 驗證 etl_job_log 有兩列記錄
    with clean_db.begin() as conn:
        stmt = select(etl_job_log).where(
            etl_job_log.c.job_name == "shareholding_tdcc"
        ).order_by(etl_job_log.c.job_id)
        result = conn.execute(stmt)
        rows = result.fetchall()

    assert len(rows) == 2
    assert rows[0].status == "success"
    assert rows[1].status == "skipped"


def test_force_可以重跑(clean_db):
    """測試 force=True 可以重跑。"""
    # 先塞入已知個股
    from twstock_etl.loaders.stock import upsert_stocks
    from twstock_etl.models import StockRecord

    with clean_db.begin() as conn:
        stock_records = [
            StockRecord(
                stock_id="2330",
                name="台積電",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
            StockRecord(
                stock_id="1101",
                name="台泥",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
            StockRecord(
                stock_id="3105",
                name="穩懋",
                market="TPEx",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
        ]
        upsert_stocks(conn, stock_records)

    # 讀取 fixture
    text = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")

    # 第一次呼叫
    load_shareholding(clean_db, csv_text=text)

    # 第二次呼叫使用 force=True
    result = load_shareholding(clean_db, csv_text=text, force=True)

    # 驗證結果
    assert result.rows == 24
    assert result.skip_reason is None


def test_parser_失敗記成_failed(clean_db):
    """測試 parser 失敗記成 failed。"""
    # 先塞入已知個股
    from twstock_etl.loaders.stock import upsert_stocks
    from twstock_etl.models import StockRecord

    with clean_db.begin() as conn:
        stock_records = [
            StockRecord(
                stock_id="2330",
                name="台積電",
                market="TWSE",
                industry=None,
                listed_date=None,
                is_etf=False,
                isin_code=None,
                cfi_code=None,
            ),
        ]
        upsert_stocks(conn, stock_records)

    # 使用無效 CSV（只有表頭）
    text = "資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%"

    # 呼叫 load_shareholding
    with pytest.raises(SourceFormatError):
        load_shareholding(clean_db, csv_text=text)

    # 驗證 etl_job_log 記錄失敗
    with clean_db.begin() as conn:
        stmt = select(etl_job_log).where(
            etl_job_log.c.job_name == "shareholding_tdcc"
        )
        result = conn.execute(stmt).first()

    assert result is not None
    assert result.status == "failed"
    assert result.error is not None
