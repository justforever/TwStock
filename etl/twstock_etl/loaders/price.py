"""價格與指數資料寫入 loader。"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from twstock_db.tables import adj_factor, daily_price, index_daily, stock
from twstock_etl.models import AdjFactorRecord, IndexRecord, PriceRecord

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


@dataclass(frozen=True)
class PriceUpsertResult:
    """日 K 寫入結果。"""

    written: int  # 實際 upsert 的筆數
    skipped_unknown: int  # 因為 stock 表沒有該代號而被丟掉的筆數


def known_stock_ids(conn: Connection) -> set[str]:
    """回傳 stock 表內所有代號（含 is_active=false）。"""
    stmt = select(stock.c.stock_id)
    result = conn.execute(stmt)
    return {row[0] for row in result}


def upsert_daily_prices(
    conn: Connection, records: Sequence[PriceRecord]
) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, trade_date) DO UPDATE 寫入日 K；stock 表沒有的代號略過。"""
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
            key = (r.stock_id, r.trade_date)
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
                "trade_date": r.trade_date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "change": r.change,
                "volume": r.volume,
                "turnover": r.turnover,
                "transactions": r.transactions,
                "source": r.source,
            }
            for r in batch
        ]

        stmt = pg_insert(daily_price).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "trade_date"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "change": stmt.excluded.change,
                "volume": stmt.excluded.volume,
                "turnover": stmt.excluded.turnover,
                "transactions": stmt.excluded.transactions,
                "source": stmt.excluded.source,
                "updated_at": func.now(),
            },
        )

        conn.execute(stmt)
        total += len(batch)

    logger.info("已寫入 %d 筆日 K", total)
    return PriceUpsertResult(written=total, skipped_unknown=len(unknown_ids))


def upsert_index_daily(conn: Connection, records: Sequence[IndexRecord]) -> int:
    """以 ON CONFLICT (index_id, trade_date) DO UPDATE 寫入指數日 K，回傳筆數。"""
    if not records:
        return 0

    total = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        rows = [
            {
                "index_id": r.index_id,
                "trade_date": r.trade_date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in batch
        ]

        stmt = pg_insert(index_daily).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["index_id", "trade_date"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "updated_at": func.now(),
            },
        )

        conn.execute(stmt)
        total += len(batch)

    logger.info("已寫入 %d 筆指數日 K", total)
    return total


def upsert_adj_factors(
    conn: Connection, records: Sequence[AdjFactorRecord]
) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, ex_date) DO UPDATE 寫入還原係數；stock 表沒有的代號略過。"""
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
            key = (r.stock_id, r.ex_date)
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
                "ex_date": r.ex_date,
                "factor": r.factor,
                "prev_close": r.prev_close,
                "reference_price": r.reference_price,
                "cash_dividend": None,  # M1 一律 None
                "stock_dividend": None,  # M1 一律 None
                "kind": r.kind,
                "source": r.source,
            }
            for r in batch
        ]

        stmt = pg_insert(adj_factor).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "ex_date"],
            set_={
                "factor": stmt.excluded.factor,
                "prev_close": stmt.excluded.prev_close,
                "reference_price": stmt.excluded.reference_price,
                "cash_dividend": stmt.excluded.cash_dividend,
                "stock_dividend": stmt.excluded.stock_dividend,
                "kind": stmt.excluded.kind,
                "source": stmt.excluded.source,
                "updated_at": func.now(),
            },
        )

        conn.execute(stmt)
        total += len(batch)

    logger.info("已寫入 %d 筆除權息係數", total)
    return PriceUpsertResult(written=total, skipped_unknown=len(unknown_ids))


def count_prices(conn: Connection, trade_date: date, source: str) -> int:
    """回傳某交易日、某來源已寫入的日 K 筆數。"""
    stmt = select(func.count()).select_from(daily_price)
    stmt = stmt.where(
        (daily_price.c.trade_date == trade_date) & (daily_price.c.source == source)
    )
    result = conn.execute(stmt).scalar()
    return result or 0


def index_trade_dates(conn: Connection, index_id: str, year: int) -> set[date]:
    """回傳某指數在某年份已有資料的所有 trade_date（給交易日曆回補用）。"""
    stmt = select(index_daily.c.trade_date).where(
        (index_daily.c.index_id == index_id)
        & (func.extract("year", index_daily.c.trade_date) == year)
    )
    result = conn.execute(stmt)
    return {row[0] for row in result}
