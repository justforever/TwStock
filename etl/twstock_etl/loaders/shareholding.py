"""集保股權分散寫入 loader。"""

import logging
from collections.abc import Sequence

from sqlalchemy import Connection
from sqlalchemy.dialects.postgresql import insert as pg_insert

from twstock_db.tables import shareholding_dist
from twstock_etl.loaders.price import PriceUpsertResult, known_stock_ids
from twstock_etl.models import ShareholdingRecord

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def upsert_shareholding(
    conn: Connection, records: Sequence[ShareholdingRecord]
) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, week_date, level) DO UPDATE 寫入；stock 表沒有的代號略過。"""
    if not records:
        return PriceUpsertResult(written=0, skipped_unknown=0)

    # 取得所有已知個股代號
    known_ids = known_stock_ids(conn)

    # 過濾出已知代號的記錄，並用主鍵去重（保留最後一筆）
    filtered_records = []
    seen_keys = {}
    unknown_ids = set()

    for r in records:
        if r.stock_id not in known_ids:
            unknown_ids.add(r.stock_id)
        else:
            key = (r.stock_id, r.week_date, r.level)
            seen_keys[key] = r
            filtered_records.append(r)

    # 記錄未知代號
    if unknown_ids:
        sample_ids = sorted(unknown_ids)[:5]
        logger.info("略過 %d 筆不在 stock 表的代號：%s", len(unknown_ids), ", ".join(sample_ids))

    # 因為去重後順序可能改變，需要重新依照去重結果排序
    filtered_records = list(seen_keys.values())

    if not filtered_records:
        return PriceUpsertResult(written=0, skipped_unknown=len(unknown_ids))

    # 寫入分批
    total = 0
    for i in range(0, len(filtered_records), BATCH_SIZE):
        batch = filtered_records[i : i + BATCH_SIZE]
        rows = [
            {
                "stock_id": r.stock_id,
                "week_date": r.week_date,
                "level": r.level,
                "holders": r.holders,
                "shares": r.shares,
                "ratio": r.ratio,
            }
            for r in batch
        ]

        stmt = pg_insert(shareholding_dist).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "week_date", "level"],
            set_={
                "holders": stmt.excluded.holders,
                "shares": stmt.excluded.shares,
                "ratio": stmt.excluded.ratio,
            },
        )

        conn.execute(stmt)
        total += len(batch)

    return PriceUpsertResult(written=total, skipped_unknown=len(unknown_ids))
