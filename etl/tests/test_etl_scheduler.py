"""ETL scheduler 測試。"""

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine

from twstock_etl.scheduler import build_scheduler


def test_scheduler_jobs():
    """測試排程器包含所有 job。"""
    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    scheduler = build_scheduler(engine)

    jobs = {j.id for j in scheduler.get_jobs()}
    expected = {
        "refresh_trading_calendar",
        "refresh_stock_list",
        "daily_price_twse",
        "daily_price_tpex",
        "index_daily_taiex",
        "adj_factor_twse",
    }
    assert jobs == expected


def test_scheduler_job_triggers():
    """測試 job 的 trigger 設定。"""
    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    scheduler = build_scheduler(engine)

    for job in scheduler.get_jobs():
        assert isinstance(job.trigger, CronTrigger)
        assert str(job.trigger.timezone) == "Asia/Taipei"


def test_run_stock_list_job_error_handling(monkeypatch):
    """測試個股清單 job 的錯誤處理。"""
    from twstock_etl.scheduler import run_stock_list_job
    from twstock_etl.errors import SourceFormatError

    call_count = 0

    def fake_refresh(engine, market, **kwargs):
        nonlocal call_count
        call_count += 1
        if market == "TWSE":
            raise SourceFormatError("測試錯誤")
        return type("obj", (object,), {"market": "TPEx", "records": 10, "deactivated": 0})()

    monkeypatch.setattr("twstock_etl.scheduler.refresh_stock_list", fake_refresh)

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    run_stock_list_job(engine)

    # 應該呼叫兩次（TWSE 失敗、TPEx 成功）
    assert call_count == 2


def test_run_daily_price_job_success(monkeypatch, caplog):
    """測試日成交 wrapper 成功路徑的 log 輸出。"""
    import logging
    from datetime import date

    from twstock_etl.jobs import PriceJobResult
    from twstock_etl.scheduler import run_daily_price_job

    def fake_load(engine, market, trade_date, **kwargs):
        return PriceJobResult(
            market=market,
            trade_date=date(2026, 9, 18),
            rows=4,
            skipped_unknown=1,
            skip_reason=None,
        )

    monkeypatch.setattr("twstock_etl.scheduler.load_daily_price", fake_load)

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    with caplog.at_level(logging.INFO, logger="twstock_etl.scheduler"):
        run_daily_price_job(engine, "TWSE")

    assert "TWSE 日成交 成功載入 4 筆" in caplog.text
    assert "Logging error" not in caplog.text
    assert "TypeError" not in caplog.text
    assert "Traceback" not in caplog.text


def test_run_daily_price_job_skip(monkeypatch, caplog):
    """被略過時要記「略過」，且不得出現任何 ERROR 紀錄。"""
    import logging
    from datetime import date

    from twstock_etl.jobs import PriceJobResult
    from twstock_etl.scheduler import run_daily_price_job

    def fake_load(engine, market, trade_date, **kwargs):
        return PriceJobResult(
            market=market,
            trade_date=date(2026, 9, 18),
            rows=0,
            skipped_unknown=0,
            skip_reason="已完成，略過",
        )

    monkeypatch.setattr("twstock_etl.scheduler.load_daily_price", fake_load)

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    with caplog.at_level(logging.INFO, logger="twstock_etl.scheduler"):
        run_daily_price_job(engine, "TWSE")

    assert "TWSE 日成交 略過：已完成，略過" in caplog.text
    assert "成功載入" not in caplog.text
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_run_trading_calendar_job_success(monkeypatch, caplog):
    """測試交易日曆 wrapper 成功路徑的 log 輸出。"""
    import logging

    from twstock_etl.jobs import CalendarLoadResult
    from twstock_etl.scheduler import run_trading_calendar_job

    def fake_refresh(engine, year, **kwargs):
        return [
            CalendarLoadResult(year=year, days=365, open_days=246, closed_days=119),
            CalendarLoadResult(year=year + 1, days=365, open_days=246, closed_days=119),
        ]

    monkeypatch.setattr(
        "twstock_etl.scheduler.refresh_calendar_with_next_year", fake_refresh
    )

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    with caplog.at_level(logging.INFO, logger="twstock_etl.scheduler"):
        run_trading_calendar_job(engine)

    assert "成功刷新 2 個年份的交易日曆" in caplog.text
    assert "Logging error" not in caplog.text
    assert "TypeError" not in caplog.text
    assert "Traceback" not in caplog.text


def test_run_index_month_job_success(monkeypatch, caplog):
    """測試指數月份 job 成功路徑的 log 輸出。"""
    import logging
    from twstock_etl.scheduler import run_index_month_job
    from twstock_etl.jobs import IndexJobResult

    def fake_load_index(engine, year, month, **kwargs):
        # 回傳 IndexJobResult 物件，不是裸 int
        return IndexJobResult(year=2026, month=9, rows=3, skip_reason=None)

    monkeypatch.setattr("twstock_etl.scheduler.load_index_month", fake_load_index)

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    with caplog.at_level(logging.INFO, logger="twstock_etl.scheduler"):
        run_index_month_job(engine)

    # 驗證 log 訊息包含正確的筆數（不是 Logging error）
    assert "TAIEX 指數 成功載入 3 筆" in caplog.text
    # 確認沒有出現 Logging error
    assert "Logging error" not in caplog.text
    assert "TypeError" not in caplog.text
    assert "Traceback" not in caplog.text


def test_run_adj_factors_job_success(monkeypatch, caplog):
    """測試除權息 job 成功路徑的 log 輸出。"""
    import logging
    from datetime import date
    from twstock_etl.scheduler import run_adj_factors_job
    from twstock_etl.jobs import AdjFactorJobResult

    def fake_load_adj(engine, start, end, **kwargs):
        # 回傳 AdjFactorJobResult 物件，不是裸 int
        # 使用 start/end 參數作為結果的日期
        return AdjFactorJobResult(start=start, end=end, rows=2, skip_reason=None)

    monkeypatch.setattr("twstock_etl.scheduler.load_adj_factors", fake_load_adj)

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    with caplog.at_level(logging.INFO, logger="twstock_etl.scheduler"):
        run_adj_factors_job(engine)

    # 驗證 log 訊息包含正確的筆數（不是 Logging error）
    assert "除權除息 成功載入 2 筆" in caplog.text
    # 確認沒有出現 Logging error
    assert "Logging error" not in caplog.text
    assert "TypeError" not in caplog.text
    assert "Traceback" not in caplog.text
