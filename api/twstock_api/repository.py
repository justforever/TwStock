from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

LIKE_ESCAPE = "!"


def escape_like(value: str) -> str:
    """跳脫 LIKE 特殊字元：! → !!、% → !%、_ → !_（先處理 !）."""
    value = value.replace("!", "!!")
    value = value.replace("%", "!%")
    value = value.replace("_", "!_")
    return value


def normalize_query(q: str) -> str:
    """strip 並把「臺」轉成「台」."""
    return q.strip().replace("臺", "台")


def search_stocks(conn: Connection, q: str, limit: int) -> list[dict[str, Any]]:
    """依規則搜尋個股，回傳 dict 清單（鍵同 StockItem 欄位）."""
    norm = normalize_query(q)
    e = escape_like(norm)

    sql = text("""
        SELECT stock_id, name, market, industry, listed_date, is_etf
        FROM stock
        WHERE is_active
          AND (stock_id ILIKE :id_prefix ESCAPE '!'
               OR replace(name, '臺', '台') ILIKE :name_contains ESCAPE '!')
        ORDER BY
          CASE
            WHEN upper(stock_id) = upper(:exact) THEN 0
            WHEN stock_id ILIKE :id_prefix ESCAPE '!' THEN 1
            WHEN replace(name, '臺', '台') ILIKE :name_prefix ESCAPE '!' THEN 2
            ELSE 3
          END,
          length(stock_id),
          stock_id
        LIMIT :limit
    """)

    rows = conn.execute(
        sql,
        {
            "exact": norm,
            "id_prefix": e + "%",
            "name_prefix": e + "%",
            "name_contains": "%" + e + "%",
            "limit": limit,
        },
    ).fetchall()

    return [dict(row._mapping) for row in rows]
