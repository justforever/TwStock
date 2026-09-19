"""既有 job 的 etl_job_log 紀錄測試（規格 §3.1、D-025）。"""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from twstock_db.tables import etl_job_log
from twstock_etl.errors import SourceFormatError
from twstock_etl.jobs import refresh_stock_list, refresh_trading_calendar


def _fixture(name: str) -> Path:
    return Path("etl/tests/fixtures") / name


def _job_rows(engine, job_name: str) -> list[tuple[str | None, str]]:
    """回傳該 job_name 的 (target_key, status) 清單。"""
    with engine.begin() as conn:
        return [
            (row.target_key, row.status)
            for row in conn.execute(
                select(etl_job_log.c.target_key, etl_job_log.c.status)
                .where(etl_job_log.c.job_name == job_name)
                .order_by(etl_job_log.c.job_id)
            )
        ]


def test_refresh_stock_list_writes_job_log(clean_db):
    """個股清單成功時要留下一列 stock_list_twse / success。"""
    html = _fixture("isin_twse_strmode2.html").read_text(encoding="utf-8")

    result = refresh_stock_list(clean_db, "TWSE", html=html)

    assert result.market == "TWSE"
    assert _job_rows(clean_db, "stock_list_twse") == [("TWSE", "success")]


def test_refresh_stock_list_guard_writes_failed(clean_db):
    """停用保護觸發時要留下一列 stock_list_twse / failed，且例外仍往外拋。"""
    html = _fixture("isin_twse_strmode2.html").read_text(encoding="utf-8")

    with pytest.raises(SourceFormatError, match="初次建庫下限"):
        refresh_stock_list(clean_db, "TWSE", html=html, deactivate=True)

    assert _job_rows(clean_db, "stock_list_twse") == [("TWSE", "failed")]


def test_refresh_trading_calendar_writes_job_log(clean_db):
    """交易日曆成功時要留下一列 trading_calendar / success。"""
    payload = json.loads(
        _fixture("twse_holiday_schedule_2026.json").read_text(encoding="utf-8")
    )

    result = refresh_trading_calendar(clean_db, 2026, payload=payload)

    assert result.year == 2026
    assert _job_rows(clean_db, "trading_calendar") == [("2026", "success")]
