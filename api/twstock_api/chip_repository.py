"""籌碼資料庫查詢模組。"""
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

MAX_LIMIT = 6000
DEFAULT_LIMIT = 2000
SHAREHOLDING_MAX_LIMIT = 520
SHAREHOLDING_DEFAULT_LIMIT = 104
DEFAULT_WINDOW_DAYS = 365
BIG_HOLDER_LEVELS = range(12, 16)   # 400 張以上（D-038）
RETAIL_LEVELS = range(1, 5)         # 15 張以下（D-038）


_LATEST_DATE_SQL: dict[str, str] = {
    "institutional": "SELECT MAX(trade_date) FROM institutional_daily WHERE stock_id = :stock_id",
    "margin":        "SELECT MAX(trade_date) FROM margin_daily WHERE stock_id = :stock_id",
    "foreign":       "SELECT MAX(trade_date) FROM foreign_holding WHERE stock_id = :stock_id",
    "shareholding":  "SELECT MAX(week_date) FROM shareholding_dist WHERE stock_id = :stock_id",
}


def latest_chip_date(conn: Connection, kind: str, stock_id: str) -> date | None:
    """該股在某張籌碼表的最新日期；kind ∈ institutional / margin / foreign / shareholding。"""
    if kind not in _LATEST_DATE_SQL:
        raise ValueError(f"不支援的籌碼種類：{kind}")

    sql_str = _LATEST_DATE_SQL[kind]
    row = conn.execute(text(sql_str), {"stock_id": stock_id}).fetchone()
    return row[0] if row and row[0] else None


def fetch_institutional(
    conn: Connection, stock_id: str, start: date, end: date, limit: int
) -> list[dict[str, Any]]:
    """取三大法人數據，依 trade_date 升冪；超過 limit 時取最新的 limit 筆。"""
    sql = text("""
        SELECT trade_date, foreign_buy, foreign_sell, foreign_net, trust_buy, trust_sell, trust_net,
               dealer_buy, dealer_sell, dealer_net, total_net
        FROM institutional_daily
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


def fetch_margin(
    conn: Connection, stock_id: str, start: date, end: date, limit: int
) -> list[dict[str, Any]]:
    """取融資融券數據，依 trade_date 升冪；超過 limit 時取最新的 limit 筆。"""
    sql = text("""
        SELECT trade_date, margin_buy, margin_sell, margin_redeem, margin_prev_balance, margin_balance,
               margin_limit, short_buy, short_sell, short_redeem, short_prev_balance, short_balance,
               short_limit, offset_amount, sbl_sell, sbl_balance
        FROM margin_daily
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


def fetch_foreign_holding(
    conn: Connection, stock_id: str, start: date, end: date, limit: int
) -> list[dict[str, Any]]:
    """取外資持股數據，依 trade_date 升冪；超過 limit 時取最新的 limit 筆。"""
    sql = text("""
        SELECT trade_date, issued_shares, holding_shares, available_shares, holding_ratio,
               available_ratio, limit_ratio
        FROM foreign_holding
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


def fetch_shareholding(
    conn: Connection, stock_id: str, start: date, end: date, limit: int
) -> list[dict[str, Any]]:
    """取集保股權分散數據，依 week_date 升冪；回傳依 week_date 分組的結果。"""
    # 先取不重複的週次（依 week_date DESC LIMIT :limit）
    weeks_sql = text("""
        SELECT DISTINCT week_date FROM shareholding_dist
        WHERE stock_id = :stock_id AND week_date >= :start AND week_date <= :end
        ORDER BY week_date DESC LIMIT :limit
    """)
    weeks_rows = conn.execute(
        weeks_sql,
        {"stock_id": stock_id, "start": start, "end": end, "limit": limit},
    ).fetchall()

    if not weeks_rows:
        return []

    weeks_list = [row[0] for row in weeks_rows]

    # 再取那些週的所有 level 資料
    rows_sql = text("""
        SELECT week_date, level, holders, shares, ratio FROM shareholding_dist
        WHERE stock_id = :stock_id AND week_date = ANY(:weeks)
        ORDER BY week_date, level
    """)
    rows = conn.execute(
        rows_sql,
        {"stock_id": stock_id, "weeks": weeks_list},
    ).fetchall()

    # 依 week_date 分組
    by_week: dict[date, list[dict[str, Any]]] = {}
    for row in rows:
        row_dict = dict(row._mapping)
        week = row_dict["week_date"]
        if week not in by_week:
            by_week[week] = []
        by_week[week].append(row_dict)

    # 每週產出結果
    result = []
    for week_date in sorted(by_week.keys()):
        levels_data = by_week[week_date]

        # 找有沒有 level 16
        has_level_16 = any(item["level"] == 16 for item in levels_data)

        if has_level_16:
            # 用 level 16 的值
            level_16 = next(item for item in levels_data if item["level"] == 16)
            total_holders = level_16["holders"]
            total_shares = level_16["shares"]
        else:
            # 用 level 1–15 的加總
            total_holders = sum(item["holders"] for item in levels_data if 1 <= item["level"] <= 15)
            total_shares = sum(item["shares"] for item in levels_data if 1 <= item["level"] <= 15)

        # 大戶比例（level 12–15）
        big_holder_ratio = sum(
            (Decimal(str(item["ratio"])) if not isinstance(item["ratio"], Decimal) else item["ratio"]) 
            for item in levels_data if item["level"] in BIG_HOLDER_LEVELS
        ) or Decimal("0")
        big_holder_ratio = big_holder_ratio.quantize(Decimal("0.0001"))

        # 散戶比例（level 1–4）
        retail_ratio = sum(
            (Decimal(str(item["ratio"])) if not isinstance(item["ratio"], Decimal) else item["ratio"]) 
            for item in levels_data if item["level"] in RETAIL_LEVELS
        ) or Decimal("0")
        retail_ratio = retail_ratio.quantize(Decimal("0.0001"))

        # 只取 level 1–15
        levels = [
            {
                "level": item["level"],
                "holders": item["holders"],
                "shares": item["shares"],
                "ratio": float(Decimal(str(item["ratio"]))),
            }
            for item in levels_data if 1 <= item["level"] <= 15
        ]

        result.append({
            "week_date": week_date,
            "total_holders": total_holders,
            "total_shares": total_shares,
            "big_holder_ratio": float(big_holder_ratio),
            "retail_ratio": float(retail_ratio),
            "levels": levels,
        })

    # 回傳依 week_date 升冪
    result.sort(key=lambda x: x["week_date"])
    return result
