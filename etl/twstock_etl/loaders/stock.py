"""個股資料寫入 loader。"""

import logging
from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import Connection, and_, func, insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from twstock_db.tables import stock
from twstock_etl.models import StockRecord

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def upsert_stocks(conn: Connection, records: Sequence[StockRecord]) -> int:
    """以 INSERT ... ON CONFLICT (stock_id) DO UPDATE 寫入個股。

    Args:
        conn: 資料庫連線
        records: 個股紀錄序列

    Returns:
        處理筆數
    """
    if not records:
        return 0

    total = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        rows = [
            {
                "stock_id": r.stock_id,
                "name": r.name,
                "market": r.market,
                "industry": r.industry or None,
                "listed_date": r.listed_date,
                "is_etf": r.is_etf,
                "isin_code": r.isin_code,
                "cfi_code": r.cfi_code,
            }
            for r in batch
        ]

        stmt = pg_insert(stock).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id"],
            set_={
                "name": stmt.excluded.name,
                "market": stmt.excluded.market,
                "industry": stmt.excluded.industry,
                "listed_date": stmt.excluded.listed_date,
                "is_etf": stmt.excluded.is_etf,
                "isin_code": stmt.excluded.isin_code,
                "cfi_code": stmt.excluded.cfi_code,
                "is_active": True,
                "updated_at": func.now(),
            },
        )

        conn.execute(stmt)
        total += len(batch)

    logger.info("已寫入 %d 筆個股", total)
    return total


def deactivate_missing(conn: Connection, market: str, keep_ids: Collection[str]) -> int:
    """把該 market 中 is_active=true 但不在 keep_ids 內的個股設為 is_active=false。

    Args:
        conn: 資料庫連線
        market: 市場別（TWSE、TPEx、ESB）
        keep_ids: 要保留為 active 的個股代號集合

    Returns:
        停用的筆數

    Raises:
        ValueError: keep_ids 為空
    """
    if not keep_ids:
        raise ValueError("keep_ids 不可為空")

    stmt = (
        stock.update()
        .where(
            and_(
                stock.c.market == market,
                stock.c.is_active,
                stock.c.stock_id.not_in(list(keep_ids)),
            )
        )
        .values(is_active=False, updated_at=func.now())
    )

    result = conn.execute(stmt)
    deactivated = result.rowcount or 0
    logger.info("已停用 %d 筆 %s 個股", deactivated, market)
    return deactivated
