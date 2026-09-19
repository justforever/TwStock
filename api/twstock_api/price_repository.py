"""價格資料庫查詢模組."""
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

MAX_LIMIT = 6000
DEFAULT_LIMIT = 2000
DEFAULT_WINDOW_DAYS = 365
INDEX_NAMES = {"TAIEX": "發行量加權股價指數"}


def get_stock(conn: Connection, stock_id: str) -> dict[str, Any] | None:
    """讀 stock 一列（含 is_active）；查無回 None。"""
    sql = text("""
        SELECT stock_id, name, market, industry, listed_date, is_etf, is_active
        FROM stock
        WHERE stock_id = :stock_id
    """)
    row = conn.execute(sql, {"stock_id": stock_id}).fetchone()
    return dict(row._mapping) if row else None


def latest_price_date(conn: Connection, stock_id: str) -> date | None:
    """該股在 daily_price 的最新 trade_date。"""
    sql = text("""
        SELECT MAX(trade_date) as latest_date
        FROM daily_price
        WHERE stock_id = :stock_id
    """)
    row = conn.execute(sql, {"stock_id": stock_id}).fetchone()
    return row[0] if row and row[0] else None


def fetch_prices(
    conn: Connection, stock_id: str, start: date, end: date, limit: int
) -> list[dict[str, Any]]:
    """讀日 K，依 trade_date 升冪；超過 limit 時取最新的 limit 筆。

    SQL 用 ORDER BY trade_date DESC LIMIT :limit 取回後在 Python 反轉，
    確保「超過上限時保留最新的資料」。
    """
    sql = text("""
        SELECT trade_date, open, high, low, close, change, volume, turnover, transactions
        FROM daily_price
        WHERE stock_id = :stock_id AND trade_date >= :start AND trade_date <= :end
        ORDER BY trade_date DESC
        LIMIT :limit
    """)
    rows = conn.execute(
        sql,
        {"stock_id": stock_id, "start": start, "end": end, "limit": limit},
    ).fetchall()
    result = [dict(row._mapping) for row in rows]
    result.reverse()
    return result


def fetch_adj_factors(
    conn: Connection, stock_id: str, until: date
) -> list[tuple[date, Decimal]]:
    """讀 ex_date <= until 的除權息係數，依 ex_date 升冪。

    注意上界要用「資料區間的最後一天」，因為只有區間內（含之後）的除權息才會影響區間內的價格；
    實作上直接取該股全部 factor 即可（一檔頂多數十列），但仍要依 ex_date 升冪。
    """
    sql = text("""
        SELECT ex_date, factor
        FROM adj_factor
        WHERE stock_id = :stock_id AND ex_date <= :until
        ORDER BY ex_date
    """)
    rows = conn.execute(sql, {"stock_id": stock_id, "until": until}).fetchall()
    return [(row[0], row[1]) for row in rows]


def latest_bar(conn: Connection, stock_id: str) -> dict[str, Any] | None:
    """該股最新一根日 K；沒有回 None。"""
    sql = text("""
        SELECT trade_date, open, high, low, close, change, volume, turnover, transactions
        FROM daily_price
        WHERE stock_id = :stock_id
        ORDER BY trade_date DESC
        LIMIT 1
    """)
    row = conn.execute(sql, {"stock_id": stock_id}).fetchone()
    return dict(row._mapping) if row else None


def fetch_index_prices(
    conn: Connection, index_id: str, start: date, end: date, limit: int
) -> list[dict[str, Any]]:
    """讀 index_daily，規則同 fetch_prices。"""
    sql = text("""
        SELECT trade_date, open, high, low, close
        FROM index_daily
        WHERE index_id = :index_id AND trade_date >= :start AND trade_date <= :end
        ORDER BY trade_date DESC
        LIMIT :limit
    """)
    rows = conn.execute(
        sql,
        {"index_id": index_id, "start": start, "end": end, "limit": limit},
    ).fetchall()
    result = [dict(row._mapping) for row in rows]
    result.reverse()
    return result
