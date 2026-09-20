"""Migration 0003（daily_price 索引）測試。"""

import pytest
from sqlalchemy import text

from twstock_db.testing import reset_database


class TestDailyPriceIndex:
    """測試 daily_price 的 (stock_id, trade_date DESC) 索引。"""

    def test_索引存在(self, clean_db):
        """驗證索引 ix_daily_price_stock_date_desc 存在。"""
        with clean_db.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE tablename = 'daily_price' AND indexname = 'ix_daily_price_stock_date_desc'"
                )
            ).fetchall()
            assert len(rows) == 1
            assert "trade_date DESC" in rows[0][0]
