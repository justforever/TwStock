"""交易日曆寫入 loader。"""

import logging
from collections.abc import Sequence

from sqlalchemy import Connection, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from twstock_db.tables import trading_calendar
from twstock_etl.models import CalendarDay

logger = logging.getLogger(__name__)


def upsert_calendar(conn: Connection, days: Sequence[CalendarDay]) -> int:
    """以 ON CONFLICT (trade_date) DO UPDATE 寫入交易日曆。

    Args:
        conn: 資料庫連線
        days: 交易日序列

    Returns:
        寫入筆數
    """
    if not days:
        return 0

    rows = [
        {"trade_date": d.trade_date, "is_open": d.is_open, "note": d.note}
        for d in days
    ]

    stmt = pg_insert(trading_calendar).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["trade_date"],
        set_={
            "is_open": stmt.excluded.is_open,
            "note": stmt.excluded.note,
            "updated_at": func.now(),
        },
    )

    conn.execute(stmt)
    logger.info("已寫入 %d 筆交易日曆", len(rows))
    return len(rows)


def insert_calendar_if_absent(conn: Connection, days: Sequence[CalendarDay]) -> int:
    """以 ON CONFLICT DO NOTHING 寫入交易日曆（不覆蓋官方來源已寫入的 note）。

    Args:
        conn: 資料庫連線
        days: 交易日序列

    Returns:
        寫入筆數
    """
    if not days:
        return 0

    rows = [
        {"trade_date": d.trade_date, "is_open": d.is_open, "note": d.note}
        for d in days
    ]

    stmt = pg_insert(trading_calendar).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["trade_date"])

    result = conn.execute(stmt)
    logger.info("已插入 %d 筆交易日曆（跳過已存在的）", result.rowcount or 0)
    return result.rowcount or 0
