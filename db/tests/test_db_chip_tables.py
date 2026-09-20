"""籌碼四表（institutional_daily、margin_daily、foreign_holding、shareholding_dist）測試。"""
from datetime import date

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert

from twstock_db.tables import (
    institutional_daily,
    margin_daily,
    foreign_holding,
    shareholding_dist,
)


class TestChipTablesExist:
    """測試四張籌碼表是否存在。"""

    def test_四張表都建起來(self, db_engine):
        """驗證 institutional_daily、margin_daily、foreign_holding、shareholding_dist 表存在。"""
        table_names = inspect(db_engine).get_table_names()
        assert "institutional_daily" in table_names
        assert "margin_daily" in table_names
        assert "foreign_holding" in table_names
        assert "shareholding_dist" in table_names


class TestInstitutionalDailySchema:
    """測試 institutional_daily 表結構。"""

    def test_institutional_daily_欄位與型別(self, clean_db):
        """驗證 institutional_daily 的欄位型別與 nullable 設定。"""
        inspector = inspect(clean_db)
        columns = {col["name"]: col for col in inspector.get_columns("institutional_daily")}

        # 驗證 foreign_net 是 bigint 且 NOT NULL
        assert columns["foreign_net"]["type"].__class__.__name__ == "BIGINT"
        assert columns["foreign_net"]["nullable"] is False

        # 驗證 source 是 character varying
        assert columns["source"]["type"].__class__.__name__ == "VARCHAR"

        # 驗證 updated_at 有預設值（透過 information_schema 查詢）
        with clean_db.begin() as conn:
            result = conn.execute(
                text(
                    "SELECT column_default FROM information_schema.columns "
                    "WHERE table_name='institutional_daily' AND column_name='updated_at'"
                )
            ).fetchone()
            assert result is not None and result[0] is not None


class TestShareholdingDistPrimaryKey:
    """測試 shareholding_dist 表主鍵。"""

    def test_shareholding_dist_主鍵三欄(self, db_engine):
        """驗證 shareholding_dist 的主鍵是 (stock_id, week_date, level)。"""
        inspector = inspect(db_engine)
        pk_columns = inspector.get_pk_constraint("shareholding_dist")["constrained_columns"]
        assert set(pk_columns) == {"stock_id", "week_date", "level"}


class TestLevelCheckConstraint:
    """測試 shareholding_dist 的 level CHECK 約束。"""

    def test_level_check_擋住_0_與_18(self, clean_db):
        """驗證 level 必須在 1–17 範圍內。"""
        # 測試 level=0 被擋住
        with clean_db.begin() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO shareholding_dist (stock_id, week_date, level, holders, shares, ratio) "
                        "VALUES (:stock_id, :week_date, :level, :holders, :shares, :ratio)"
                    ),
                    {
                        "stock_id": "2330",
                        "week_date": "2026-09-18",
                        "level": 0,
                        "holders": 100,
                        "shares": 1000,
                        "ratio": 1.0,
                    },
                )

        # 測試 level=18 被擋住
        with clean_db.begin() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO shareholding_dist (stock_id, week_date, level, holders, shares, ratio) "
                        "VALUES (:stock_id, :week_date, :level, :holders, :shares, :ratio)"
                    ),
                    {
                        "stock_id": "2330",
                        "week_date": "2026-09-18",
                        "level": 18,
                        "holders": 100,
                        "shares": 1000,
                        "ratio": 1.0,
                    },
                )

        # 測試 level=17 成功
        with clean_db.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO shareholding_dist (stock_id, week_date, level, holders, shares, ratio) "
                    "VALUES (:stock_id, :week_date, :level, :holders, :shares, :ratio)"
                ),
                {
                    "stock_id": "2330",
                    "week_date": "2026-09-18",
                    "level": 17,
                    "holders": 100,
                    "shares": 1000,
                    "ratio": 1.0,
                },
            )
            result = conn.execute(text("SELECT level FROM shareholding_dist WHERE stock_id='2330'")).fetchone()
            assert result[0] == 17


class TestMarginDailySourceCheck:
    """測試 margin_daily 的 source CHECK 約束。"""

    def test_margin_daily_source_check(self, clean_db):
        """驗證 margin_daily source 必須是 TWSE 或 TPEx。"""
        # 測試無效的 source 被擋住
        with clean_db.begin() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO margin_daily (stock_id, trade_date, source) "
                        "VALUES (:stock_id, :trade_date, :source)"
                    ),
                    {"stock_id": "2330", "trade_date": "2026-09-18", "source": "OTHER"},
                )

        # 測試 TPEx 成功
        with clean_db.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO margin_daily (stock_id, trade_date, source) "
                    "VALUES (:stock_id, :trade_date, :source)"
                ),
                {"stock_id": "2330", "trade_date": "2026-09-18", "source": "TPEx"},
            )
            result = conn.execute(
                text("SELECT source FROM margin_daily WHERE stock_id='2330'")
            ).fetchone()
            assert result[0] == "TPEx"


class TestUpsert:
    """測試 upsert 功能。"""

    def test_可以_upsert_同一個主鍵(self, clean_db):
        """驗證可以用 ON CONFLICT DO UPDATE 重複寫入同一主鍵。"""
        with clean_db.begin() as conn:
            # 第一次插入
            stmt = pg_insert(institutional_daily).values(
                stock_id="2330",
                trade_date=date(2026, 9, 18),
                foreign_buy=10000000,
                foreign_sell=5000000,
                foreign_net=5000000,
                trust_buy=1000000,
                trust_sell=500000,
                trust_net=500000,
                dealer_buy=500000,
                dealer_sell=500000,
                dealer_net=0,
                total_net=6000000,
                source="TWSE",
            )
            conn.execute(stmt)

            # 檢查第一次的值
            result = conn.execute(
                text("SELECT foreign_net FROM institutional_daily WHERE stock_id='2330'")
            ).fetchone()
            assert result[0] == 5000000

            # 第二次 upsert（更新）
            stmt = pg_insert(institutional_daily).values(
                stock_id="2330",
                trade_date=date(2026, 9, 18),
                foreign_buy=15000000,
                foreign_sell=8000000,
                foreign_net=7000000,
                trust_buy=2000000,
                trust_sell=1000000,
                trust_net=1000000,
                dealer_buy=1000000,
                dealer_sell=1000000,
                dealer_net=0,
                total_net=8000000,
                source="TWSE",
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["stock_id", "trade_date"],
                set_={"foreign_net": 7000000},
            )
            conn.execute(stmt)

            # 檢查已更新
            result = conn.execute(
                text("SELECT foreign_net FROM institutional_daily WHERE stock_id='2330'")
            ).fetchone()
            assert result[0] == 7000000

            # 確認總行數仍為 1
            count = conn.execute(text("SELECT count(*) FROM institutional_daily")).fetchone()[0]
            assert count == 1
