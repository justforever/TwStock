"""ETL scheduler 測試。"""

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine

from twstock_etl.scheduler import build_scheduler


def test_scheduler_jobs():
    """測試排程器包含兩個 job。"""
    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    scheduler = build_scheduler(engine)

    jobs = {j.id for j in scheduler.get_jobs()}
    assert jobs == {"refresh_stock_list", "refresh_trading_calendar"}


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
