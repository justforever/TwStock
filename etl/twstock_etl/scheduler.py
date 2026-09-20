"""APScheduler 排程定義。"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import Engine

from twstock_etl.jobs import (
    load_adj_factors,
    load_daily_price,
    load_index_month,
    refresh_calendar_with_next_year,
    refresh_stock_list,
)

logger = logging.getLogger(__name__)

TAIPEI = ZoneInfo("Asia/Taipei")


def _log_job_outcome(what: str, result) -> None:
    """統一記錄 job 結果：被略過記「略過」，實際執行記筆數。

    result 需有 rows: int 與 skip_reason: str | None（見規格 §3 共同契約、D-028）。

    Args:
        what: 這次 job 的描述，例如「2026-09-18 TWSE 日成交」
        result: PriceJobResult / IndexJobResult / AdjFactorJobResult
    """
    if result.skip_reason is not None:
        logger.info("%s 略過：%s", what, result.skip_reason)
    else:
        logger.info("%s 成功載入 %d 筆", what, result.rows)


def run_stock_list_job(engine: Engine) -> None:
    """依序刷新 TWSE、TPEx 個股清單（deactivate=True）；單一市場失敗只記 log 不中斷另一個。

    Args:
        engine: SQLAlchemy Engine
    """
    for market in ["TWSE", "TPEx"]:
        try:
            result = refresh_stock_list(engine, market, deactivate=True)
            logger.info(
                "成功刷新 %s 個股清單：%d 筆，停用 %d 筆",
                result.market,
                result.records,
                result.deactivated,
            )
        except Exception:
            logger.exception("刷新 %s 個股清單失敗", market)


def run_trading_calendar_job(engine: Engine) -> None:
    """刷新台北時間今年與明年的交易日曆；失敗只記 log。

    Args:
        engine: SQLAlchemy Engine
    """
    try:
        year = datetime.now(TAIPEI).year
        results = refresh_calendar_with_next_year(engine, year)
        logger.info("成功刷新 %d 個年份的交易日曆", len(results))
    except Exception:
        logger.exception("刷新交易日曆失敗")


def run_daily_price_job(engine: Engine, market: str) -> None:
    """載入單日日成交；失敗只記 log。

    Args:
        engine: SQLAlchemy Engine
        market: 市場別
    """
    try:
        today = datetime.now(TAIPEI).date()
        _log_job_outcome(
            f"{today} {market} 日成交",
            load_daily_price(engine, market, today),
        )
    except Exception:
        logger.exception("載入 %s 日成交失敗", market)


def run_index_month_job(engine: Engine) -> None:
    """載入當月 TAIEX 指數；失敗只記 log。

    Args:
        engine: SQLAlchemy Engine
    """
    try:
        now = datetime.now(TAIPEI)
        year, month = now.year, now.month
        _log_job_outcome(
            f"{year:04d}-{month:02d} TAIEX 指數",
            load_index_month(engine, year, month, force=True),
        )
    except Exception:
        logger.exception("載入 TAIEX 指數失敗")


def run_adj_factors_job(engine: Engine) -> None:
    """載入最近 7 天的除權除息；失敗只記 log。

    Args:
        engine: SQLAlchemy Engine
    """
    try:
        today = datetime.now(TAIPEI).date()
        start = today - timedelta(days=7)
        end = today
        _log_job_outcome(
            f"{start} 至 {end} 除權除息",
            load_adj_factors(engine, start, end),
        )
    except Exception:
        logger.exception("載入除權除息失敗")


def build_scheduler(engine: Engine) -> BlockingScheduler:
    """建立（未啟動的）排程器並註冊所有 job。

    Args:
        engine: SQLAlchemy Engine

    Returns:
        BlockingScheduler 實例
    """
    scheduler = BlockingScheduler(timezone=TAIPEI)

    # 交易日曆：每日 07:30 台北時間（啟動即跑一次）
    scheduler.add_job(
        run_trading_calendar_job,
        trigger=CronTrigger(hour=7, minute=30, timezone=TAIPEI),
        args=[engine],
        id="refresh_trading_calendar",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
        next_run_time=datetime.now(TAIPEI),
    )

    # 個股清單：每日 08:00 台北時間（啟動即跑一次）
    scheduler.add_job(
        run_stock_list_job,
        trigger=CronTrigger(hour=8, minute=0, timezone=TAIPEI),
        args=[engine],
        id="refresh_stock_list",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
        next_run_time=datetime.now(TAIPEI),
    )

    # 日成交（上市）：每日 15:35、17:35、19:35 台北時間
    scheduler.add_job(
        run_daily_price_job,
        trigger=CronTrigger(hour="15,17,19", minute=35, timezone=TAIPEI),
        args=[engine, "TWSE"],
        id="daily_price_twse",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 日成交（上櫃）：每日 15:45、17:45、19:45 台北時間
    scheduler.add_job(
        run_daily_price_job,
        trigger=CronTrigger(hour="15,17,19", minute=45, timezone=TAIPEI),
        args=[engine, "TPEx"],
        id="daily_price_tpex",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 指數日 K（當月）：每日 15:55、17:55、19:55 台北時間
    scheduler.add_job(
        run_index_month_job,
        trigger=CronTrigger(hour="15,17,19", minute=55, timezone=TAIPEI),
        args=[engine],
        id="index_daily_taiex",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # 除權除息：每日 16:10 台北時間
    scheduler.add_job(
        run_adj_factors_job,
        trigger=CronTrigger(hour=16, minute=10, timezone=TAIPEI),
        args=[engine],
        id="adj_factor_twse",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    return scheduler
