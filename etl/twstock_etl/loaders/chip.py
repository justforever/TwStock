"""籌碼三表寫入 loader。"""

import logging
from collections.abc import Sequence

from sqlalchemy import Connection, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from twstock_db.tables import (
    foreign_holding,
    institutional_daily,
    margin_daily,
)
from twstock_etl.loaders.price import PriceUpsertResult, known_stock_ids
from twstock_etl.models import (
    ForeignHoldingRecord,
    InstitutionalRecord,
    MarginRecord,
    SblRecord,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def upsert_institutional(
    conn: Connection, records: Sequence[InstitutionalRecord]
) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, trade_date) DO UPDATE 寫入 institutional_daily。"""
    if not records:
        return PriceUpsertResult(written=0, skipped_unknown=0)

    known_ids = known_stock_ids(conn)

    filtered_records = []
    seen_keys = {}
    unknown_ids = set()

    for r in records:
        if r.stock_id not in known_ids:
            unknown_ids.add(r.stock_id)
        else:
            key = (r.stock_id, r.trade_date)
            seen_keys[key] = r

    if unknown_ids:
        sample_ids = sorted(unknown_ids)[:5]
        logger.info("略過 %d 筆不在 stock 表的代號：%s", len(unknown_ids), ", ".join(sample_ids))

    filtered_records = list(seen_keys.values())

    if not filtered_records:
        return PriceUpsertResult(written=0, skipped_unknown=len(unknown_ids))

    total = 0
    for i in range(0, len(filtered_records), BATCH_SIZE):
        batch = filtered_records[i : i + BATCH_SIZE]
        rows = [
            {
                "stock_id": r.stock_id,
                "trade_date": r.trade_date,
                "foreign_buy": r.foreign_buy,
                "foreign_sell": r.foreign_sell,
                "foreign_net": r.foreign_net,
                "trust_buy": r.trust_buy,
                "trust_sell": r.trust_sell,
                "trust_net": r.trust_net,
                "dealer_buy": r.dealer_buy,
                "dealer_sell": r.dealer_sell,
                "dealer_net": r.dealer_net,
                "total_net": r.total_net,
                "source": r.source,
            }
            for r in batch
        ]

        stmt = (
            pg_insert(institutional_daily)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["stock_id", "trade_date"],
                set_={
                    "foreign_buy": pg_insert(institutional_daily).excluded.foreign_buy,
                    "foreign_sell": pg_insert(institutional_daily).excluded.foreign_sell,
                    "foreign_net": pg_insert(institutional_daily).excluded.foreign_net,
                    "trust_buy": pg_insert(institutional_daily).excluded.trust_buy,
                    "trust_sell": pg_insert(institutional_daily).excluded.trust_sell,
                    "trust_net": pg_insert(institutional_daily).excluded.trust_net,
                    "dealer_buy": pg_insert(institutional_daily).excluded.dealer_buy,
                    "dealer_sell": pg_insert(institutional_daily).excluded.dealer_sell,
                    "dealer_net": pg_insert(institutional_daily).excluded.dealer_net,
                    "total_net": pg_insert(institutional_daily).excluded.total_net,
                    "source": pg_insert(institutional_daily).excluded.source,
                    "updated_at": func.now(),
                },
            )
        )
        conn.execute(stmt)
        total += len(batch)

    return PriceUpsertResult(written=total, skipped_unknown=len(unknown_ids))


def upsert_margin(
    conn: Connection, records: Sequence[MarginRecord]
) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, trade_date) DO UPDATE 寫入 margin_daily 的融資融券欄位。"""
    if not records:
        return PriceUpsertResult(written=0, skipped_unknown=0)

    known_ids = known_stock_ids(conn)

    filtered_records = []
    seen_keys = {}
    unknown_ids = set()

    for r in records:
        if r.stock_id not in known_ids:
            unknown_ids.add(r.stock_id)
        else:
            key = (r.stock_id, r.trade_date)
            seen_keys[key] = r

    if unknown_ids:
        sample_ids = sorted(unknown_ids)[:5]
        logger.info("略過 %d 筆不在 stock 表的代號：%s", len(unknown_ids), ", ".join(sample_ids))

    filtered_records = list(seen_keys.values())

    if not filtered_records:
        return PriceUpsertResult(written=0, skipped_unknown=len(unknown_ids))

    total = 0
    for i in range(0, len(filtered_records), BATCH_SIZE):
        batch = filtered_records[i : i + BATCH_SIZE]
        rows = [
            {
                "stock_id": r.stock_id,
                "trade_date": r.trade_date,
                "margin_buy": r.margin_buy,
                "margin_sell": r.margin_sell,
                "margin_redeem": r.margin_redeem,
                "margin_prev_balance": r.margin_prev_balance,
                "margin_balance": r.margin_balance,
                "margin_limit": r.margin_limit,
                "short_buy": r.short_buy,
                "short_sell": r.short_sell,
                "short_redeem": r.short_redeem,
                "short_prev_balance": r.short_prev_balance,
                "short_balance": r.short_balance,
                "short_limit": r.short_limit,
                "offset_amount": r.offset_amount,
                "source": r.source,
            }
            for r in batch
        ]

        stmt = (
            pg_insert(margin_daily)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["stock_id", "trade_date"],
                set_={
                    "margin_buy": pg_insert(margin_daily).excluded.margin_buy,
                    "margin_sell": pg_insert(margin_daily).excluded.margin_sell,
                    "margin_redeem": pg_insert(margin_daily).excluded.margin_redeem,
                    "margin_prev_balance": pg_insert(margin_daily).excluded.margin_prev_balance,
                    "margin_balance": pg_insert(margin_daily).excluded.margin_balance,
                    "margin_limit": pg_insert(margin_daily).excluded.margin_limit,
                    "short_buy": pg_insert(margin_daily).excluded.short_buy,
                    "short_sell": pg_insert(margin_daily).excluded.short_sell,
                    "short_redeem": pg_insert(margin_daily).excluded.short_redeem,
                    "short_prev_balance": pg_insert(margin_daily).excluded.short_prev_balance,
                    "short_balance": pg_insert(margin_daily).excluded.short_balance,
                    "short_limit": pg_insert(margin_daily).excluded.short_limit,
                    "offset_amount": pg_insert(margin_daily).excluded.offset_amount,
                    "source": pg_insert(margin_daily).excluded.source,
                    "updated_at": func.now(),
                },
            )
        )
        conn.execute(stmt)
        total += len(batch)

    return PriceUpsertResult(written=total, skipped_unknown=len(unknown_ids))


def upsert_sbl(
    conn: Connection, records: Sequence[SblRecord]
) -> PriceUpsertResult:
    """把借券資料寫進 margin_daily 的 sbl_* 兩欄；不碰融資融券欄位（D-037）。"""
    if not records:
        return PriceUpsertResult(written=0, skipped_unknown=0)

    known_ids = known_stock_ids(conn)

    filtered_records = []
    seen_keys = {}
    unknown_ids = set()

    for r in records:
        if r.stock_id not in known_ids:
            unknown_ids.add(r.stock_id)
        else:
            key = (r.stock_id, r.trade_date)
            seen_keys[key] = r

    if unknown_ids:
        sample_ids = sorted(unknown_ids)[:5]
        logger.info("略過 %d 筆不在 stock 表的代號：%s", len(unknown_ids), ", ".join(sample_ids))

    filtered_records = list(seen_keys.values())

    if not filtered_records:
        return PriceUpsertResult(written=0, skipped_unknown=len(unknown_ids))

    total = 0
    for i in range(0, len(filtered_records), BATCH_SIZE):
        batch = filtered_records[i : i + BATCH_SIZE]
        rows = [
            {
                "stock_id": r.stock_id,
                "trade_date": r.trade_date,
                "sbl_sell": r.sbl_sell,
                "sbl_balance": r.sbl_balance,
                "source": r.source,
            }
            for r in batch
        ]

        stmt = (
            pg_insert(margin_daily)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["stock_id", "trade_date"],
                set_={
                    "sbl_sell": pg_insert(margin_daily).excluded.sbl_sell,
                    "sbl_balance": pg_insert(margin_daily).excluded.sbl_balance,
                    "updated_at": func.now(),
                },
            )
        )
        conn.execute(stmt)
        total += len(batch)

    return PriceUpsertResult(written=total, skipped_unknown=len(unknown_ids))


def upsert_foreign_holding(
    conn: Connection, records: Sequence[ForeignHoldingRecord]
) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, trade_date) DO UPDATE 寫入 foreign_holding。"""
    if not records:
        return PriceUpsertResult(written=0, skipped_unknown=0)

    known_ids = known_stock_ids(conn)

    filtered_records = []
    seen_keys = {}
    unknown_ids = set()

    for r in records:
        if r.stock_id not in known_ids:
            unknown_ids.add(r.stock_id)
        else:
            key = (r.stock_id, r.trade_date)
            seen_keys[key] = r

    if unknown_ids:
        sample_ids = sorted(unknown_ids)[:5]
        logger.info("略過 %d 筆不在 stock 表的代號：%s", len(unknown_ids), ", ".join(sample_ids))

    filtered_records = list(seen_keys.values())

    if not filtered_records:
        return PriceUpsertResult(written=0, skipped_unknown=len(unknown_ids))

    total = 0
    for i in range(0, len(filtered_records), BATCH_SIZE):
        batch = filtered_records[i : i + BATCH_SIZE]
        rows = [
            {
                "stock_id": r.stock_id,
                "trade_date": r.trade_date,
                "issued_shares": r.issued_shares,
                "holding_shares": r.holding_shares,
                "available_shares": r.available_shares,
                "holding_ratio": r.holding_ratio,
                "available_ratio": r.available_ratio,
                "limit_ratio": r.limit_ratio,
                "source": r.source,
            }
            for r in batch
        ]

        stmt = (
            pg_insert(foreign_holding)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["stock_id", "trade_date"],
                set_={
                    "issued_shares": pg_insert(foreign_holding).excluded.issued_shares,
                    "holding_shares": pg_insert(foreign_holding).excluded.holding_shares,
                    "available_shares": pg_insert(foreign_holding).excluded.available_shares,
                    "holding_ratio": pg_insert(foreign_holding).excluded.holding_ratio,
                    "available_ratio": pg_insert(foreign_holding).excluded.available_ratio,
                    "limit_ratio": pg_insert(foreign_holding).excluded.limit_ratio,
                    "source": pg_insert(foreign_holding).excluded.source,
                    "updated_at": func.now(),
                },
            )
        )
        conn.execute(stmt)
        total += len(batch)

    return PriceUpsertResult(written=total, skipped_unknown=len(unknown_ids))
