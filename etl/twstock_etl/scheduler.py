"""APScheduler 排程定義。"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import Engine

from twstock_etl.jobs import refresh_stock_list, refresh_trading_calendar

logger = logging.getLogger(__name__)

TAIPEI = ZoneInfo("Asia/Taipei")


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


def run_calendar_job(engine: Engine) -> None:
    """刷新台北時間今年的交易日曆；失敗只記 log。

    Args:
        engine: SQLAlchemy Engine
    """
    try:
        year = datetime.now(TAIPEI).year
        result = refresh_trading_calendar(engine, year)
        logger.info(
            "成功刷新 %d 年交易日曆：%d 天，開市 %d 天",
            result.year,
            result.days,
            result.open_days,
        )
    except Exception:
        logger.exception("刷新交易日曆失敗")


def build_scheduler(engine: Engine) -> BlockingScheduler:
    """建立（未啟動的）排程器並註冊 M0 的兩個 job。

    Args:
        engine: SQLAlchemy Engine

    Returns:
        BlockingScheduler 實例
    """
    scheduler = BlockingScheduler(timezone=TAIPEI)

    # 個股清單：每日 08:00 台北時間
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

    # 交易日曆：每日 07:30 台北時間
    scheduler.add_job(
        run_calendar_job,
        trigger=CronTrigger(hour=7, minute=30, timezone=TAIPEI),
        args=[engine],
        id="refresh_trading_calendar",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
        next_run_time=datetime.now(TAIPEI),
    )

    return scheduler
