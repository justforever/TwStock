"""TimescaleDB 偵測與設定工具。"""
import logging
import re
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

logger = logging.getLogger(__name__)

NEW_HYPERTABLE_SQL = """
SELECT create_hypertable(
    CAST(:table AS regclass),
    by_range(CAST(:time_column AS name), CAST(:interval AS interval)),
    if_not_exists => TRUE,
    migrate_data  => TRUE
)
"""

LEGACY_HYPERTABLE_SQL = """
SELECT create_hypertable(
    CAST(:table AS regclass), :time_column,
    chunk_time_interval => CAST(:interval AS interval),
    if_not_exists => TRUE,
    migrate_data  => TRUE
)
"""


def timescaledb_available(conn: Connection) -> bool:
    """此 PostgreSQL 是否安裝了 timescaledb 擴充套件檔（pg_available_extensions）。"""
    result = conn.execute(
        text("SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'")
    )
    return result.scalar() is not None


def timescaledb_installed(conn: Connection) -> bool:
    """目前資料庫是否已 CREATE EXTENSION timescaledb（pg_extension）。"""
    result = conn.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")
    )
    return result.scalar() is not None


def ensure_timescaledb(conn: Connection) -> bool:
    """若可用則 CREATE EXTENSION IF NOT EXISTS timescaledb 並回傳 True；不可用回傳 False 並記 INFO log。"""
    if not timescaledb_available(conn):
        logger.info("TimescaleDB 不可用，維持一般資料表")
        return False

    conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    return True


def create_hypertable_if_available(
    conn: Connection, table: str, time_column: str, chunk_interval: str = "1 month"
) -> bool:
    """若已安裝 timescaledb，將 table 轉為 hypertable 並回傳 True；否則不做事回傳 False。

    先用 TimescaleDB 2.13+ 的 by_range() 簽名，失敗時退回 2.13 之前的舊簽名。
    """
    identifier_pattern = re.compile(r"^[a-z_][a-z0-9_]*$")
    if not identifier_pattern.match(table) or not identifier_pattern.match(time_column):
        raise ValueError(f"無效的識別字：table={table!r}, time_column={time_column!r}")

    if not timescaledb_installed(conn):
        logger.info("未安裝 TimescaleDB，%s 維持一般資料表", table)
        return False

    params = {"table": table, "time_column": time_column, "interval": chunk_interval}
    try:
        with conn.begin_nested():
            conn.execute(text(NEW_HYPERTABLE_SQL), params)
        logger.info("已將 %s 轉為 hypertable（by_range 簽名）", table)
        return True
    except DBAPIError as exc:  # noqa: BLE001 - 舊版 TimescaleDB 沒有 by_range()
        logger.warning("by_range() 簽名失敗，改用舊簽名重試：%s", exc)

    with conn.begin_nested():
        conn.execute(text(LEGACY_HYPERTABLE_SQL), params)
    logger.info("已將 %s 轉為 hypertable（舊簽名）", table)
    return True
