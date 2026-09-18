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
    assert "成功載入 2026-09 TAIEX 指數：3 筆" in caplog.text
    # 確認沒有出現 Logging error
    assert "Logging error" not in caplog.text
    assert "TypeError" not in caplog.text


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
    assert "除權除息：2 筆" in caplog.text
    # 確認沒有出現 Logging error
    assert "Logging error" not in caplog.text
    assert "TypeError" not in caplog.text
