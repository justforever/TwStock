"""回補腳本測試。"""

import io
import re
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import insert, select

from twstock_db.tables import index_daily, stock, trading_calendar
from twstock_etl.backfill import (
    BackfillAborted,
    BackfillOptions,
    RateLimiter,
    backfill_calendar,
    backfill_exright,
    backfill_index,
    backfill_prices,
)
from twstock_etl.models import CalendarDay


def test_rate_limiter_first_wait_no_sleep() -> None:
    """第一次 wait() 不睡覺。"""
    sleep_calls = []
    clock_times = [0.0, 0.5, 3.5]
    clock_index = [0]

    def mock_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    def mock_clock() -> float:
        result = clock_times[clock_index[0]]
        clock_index[0] += 1
        return result

    limiter = RateLimiter(3.0, sleep=mock_sleep, clock=mock_clock)
    limiter.wait()  # 第一次：clock() = 0.0，no sleep
    assert sleep_calls == []


def test_rate_limiter_second_wait_sleeps() -> None:
    """第二次 wait() 睡到補滿間隔。"""
    sleep_calls = []
    clock_times = [0.0, 0.0, 0.5, 3.6]
    clock_index = [0]

    def mock_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    def mock_clock() -> float:
        result = clock_times[clock_index[0]]
        clock_index[0] += 1
        return result

    limiter = RateLimiter(3.0, sleep=mock_sleep, clock=mock_clock)
    limiter.wait()  # 第一次：clock()=0.0, last_wait_time=0.0
    limiter.wait()  # 第二次：clock()=0.5, elapsed=0.5, sleep 2.5 秒, clock()=3.6
    assert len(sleep_calls) == 1
    assert 2.4 < sleep_calls[0] < 2.6


def test_backfill_prices_happy_path(clean_db: "Engine") -> None:
    """第一次回補 TWSE 3 天，應成功並寫入 15 筆（3 天 × 5 筆/天）。"""
    # 準備日曆和股票
    with clean_db.begin() as conn:
        for day in [date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)]:
            conn.execute(
                insert(trading_calendar).values(
                    trade_date=day, is_open=True, note=None
                )
            )
        # 加入 fixture 中出現的股票
        for stock_id in ["1101", "2317", "2330", "2834", "2882", "0050"]:
            conn.execute(
                insert(stock).values(
                    stock_id=stock_id,
                    name="test",
                    market="TWSE",
                    is_active=True,
                )
            )

    output = io.StringIO()
    options = BackfillOptions(
        sleep_seconds=0,
        source_dir=Path("etl/tests/fixtures"),
        out=output,
    )

    summary = backfill_prices(
        clean_db, "TWSE", date(2026, 9, 16), date(2026, 9, 18), options
    )

    assert summary.total == 3
    assert summary.done == 3
    assert summary.skipped == 0
    assert summary.failed == 0
    assert summary.rows == 15

    # 檢查輸出格式
    lines = output.getvalue().strip().split("\n")
    assert len(lines) == 4  # 3 個進度行 + 1 個總結行

    # 檢查進度行格式
    for line in lines[:3]:
        assert re.match(r"^\[\s*\d+/\s*\d+\]", line)


def test_backfill_prices_skip_on_second_run(clean_db: "Engine") -> None:
    """第二次回補相同日期，應全部略過。"""
    # 準備日曆和股票
    with clean_db.begin() as conn:
        for day in [date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)]:
            conn.execute(
                insert(trading_calendar).values(
                    trade_date=day, is_open=True, note=None
                )
            )
        # 加入 fixture 中出現的股票
        for stock_id in ["1101", "2317", "2330", "2834", "2882", "0050"]:
            conn.execute(
                insert(stock).values(
                    stock_id=stock_id,
                    name="test",
                    market="TWSE",
                    is_active=True,
                )
            )

    output = io.StringIO()
    options = BackfillOptions(
        sleep_seconds=0,
        source_dir=Path("etl/tests/fixtures"),
        out=output,
    )

    # 第一次
    summary1 = backfill_prices(
        clean_db, "TWSE", date(2026, 9, 16), date(2026, 9, 18), options
    )
    assert summary1.done == 3

    # 第二次
    output2 = io.StringIO()
    options2 = BackfillOptions(
        sleep_seconds=0,
        source_dir=Path("etl/tests/fixtures"),
        out=output2,
    )
    summary2 = backfill_prices(
        clean_db, "TWSE", date(2026, 9, 16), date(2026, 9, 18), options2
    )

    assert summary2.done == 0
    assert summary2.skipped == 3

    # 檢查輸出都含 skip
    output_text = output2.getvalue()
    skip_count = output_text.count("skip")
    assert skip_count == 3


def test_backfill_prices_missing_source_file(clean_db: "Engine") -> None:
    """source_dir 少一個檔案時，該日失敗，其他日成功。"""
    # 準備日曆
    with clean_db.begin() as conn:
        for day in [date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)]:
            conn.execute(
                insert(trading_calendar).values(
                    trade_date=day, is_open=True, note=None
                )
            )

    # 用不存在的 fixture 目錄
    output = io.StringIO()
    options = BackfillOptions(
        sleep_seconds=0,
        source_dir=Path("/nonexistent/fixtures"),
        out=output,
        max_failures=10,
    )

    summary = backfill_prices(
        clean_db, "TWSE", date(2026, 9, 16), date(2026, 9, 18), options
    )

    assert summary.failed == 3
    assert "FAIL" in output.getvalue()


def test_backfill_prices_max_failures_exceeded(clean_db: "Engine") -> None:
    """超過 max_failures 時應拋 BackfillAborted。"""
    # 準備日曆
    with clean_db.begin() as conn:
        for day in [date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)]:
            conn.execute(
                insert(trading_calendar).values(
                    trade_date=day, is_open=True, note=None
                )
            )

    output = io.StringIO()
    options = BackfillOptions(
        sleep_seconds=0,
        source_dir=Path("/nonexistent/fixtures"),
        max_failures=0,  # 不容許任何失敗
        out=output,
    )

    with pytest.raises(BackfillAborted):
        backfill_prices(
            clean_db, "TWSE", date(2026, 9, 16), date(2026, 9, 18), options
        )


def test_backfill_prices_dry_run(clean_db: "Engine") -> None:
    """dry_run 模式應不寫入 DB、rows == 0、輸出含 dry-run。"""
    # 準備日曆
    with clean_db.begin() as conn:
        for day in [date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)]:
            conn.execute(
                insert(trading_calendar).values(
                    trade_date=day, is_open=True, note=None
                )
            )

    output = io.StringIO()
    options = BackfillOptions(
        sleep_seconds=0,
        source_dir=Path("etl/tests/fixtures"),
        dry_run=True,
        out=output,
    )

    summary = backfill_prices(
        clean_db, "TWSE", date(2026, 9, 16), date(2026, 9, 18), options
    )

    assert summary.done == 3
    assert summary.rows == 0
    assert "dry-run" in output.getvalue()


def test_backfill_index_happy_path(clean_db: "Engine") -> None:
    """回補指數一個月應成功。"""
    output = io.StringIO()
    options = BackfillOptions(
        sleep_seconds=0,
        source_dir=Path("etl/tests/fixtures"),
        out=output,
    )

    summary = backfill_index(clean_db, "2026-09", "2026-09", options)

    assert summary.total == 1
    assert summary.done == 1
    assert summary.failed == 0
    assert summary.rows == 3  # TAIEX_index_202609.json 有 3 筆


def test_backfill_exright_happy_path(clean_db: "Engine") -> None:
    """回補除權息一個月應成功。"""
    # 加入 fixture 中出現的股票
    with clean_db.begin() as conn:
        for stock_id in ["1101", "2330", "2317"]:
            conn.execute(
                insert(stock).values(
                    stock_id=stock_id,
                    name="test",
                    market="TWSE",
                    is_active=True,
                )
            )

    output = io.StringIO()
    options = BackfillOptions(
        sleep_seconds=0,
        source_dir=Path("etl/tests/fixtures"),
        out=output,
    )

    summary = backfill_exright(
        clean_db, date(2026, 9, 1), date(2026, 9, 30), options
    )

    assert summary.total == 1
    assert summary.done == 1
    assert summary.failed == 0
    assert summary.rows == 2  # exright_20260901_20260930.json 有 2 筆（1101 和 2330，2317 被跳過）


def test_backfill_calendar_happy_path(clean_db: "Engine") -> None:
    """回補日曆：先塞 250 筆 2025 年指數資料，應反推出 365 天日曆、250 開市日。"""
    # 先塞 250 筆 index_daily 假資料
    with clean_db.begin() as conn:
        for i in range(250):
            d = date(2025, 1, 1)
            new_date = d.replace(year=d.year, month=1, day=1) + __import__(
                "datetime"
            ).timedelta(days=i)
            if new_date.year == 2025:
                conn.execute(
                    insert(index_daily).values(
                        index_id="TAIEX",
                        trade_date=new_date,
                        open=24500,
                        high=24680,
                        low=24450,
                        close=24600,
                        volume=None,
                    )
                )

    output = io.StringIO()
    options = BackfillOptions(
        sleep_seconds=0,
        out=output,
    )

    summary = backfill_calendar(clean_db, 2025, 2025, options)

    assert summary.total == 1
    assert summary.done == 1
    assert summary.rows == 365  # 365 天

    # 驗證日曆已寫入
    with clean_db.begin() as conn:
        result = conn.execute(
            select(trading_calendar).where(
                (trading_calendar.c.trade_date >= date(2025, 1, 1))
                & (trading_calendar.c.trade_date <= date(2025, 12, 31))
            )
        )
        days = list(result)
        assert len(days) == 365
        open_days = sum(1 for d in days if d.is_open)
        assert open_days == 250
