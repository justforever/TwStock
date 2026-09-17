"""資料庫 migration 測試。"""
from datetime import date

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from twstock_db.tables import metadata
from twstock_db.testing import reset_database


class TestTablesExist:
    """測試表是否存在。"""

    def test_tables_exist(self, db_engine):
        """驗證 stock、trading_calendar、alembic_version 表存在。"""
        table_names = inspect(db_engine).get_table_names()
        assert "stock" in table_names
        assert "trading_calendar" in table_names
        assert "alembic_version" in table_names


class TestTablesPyMatchesDatabase:
    """測試 Python 表定義與資料庫結構一致。"""

    def test_tables_py_matches_database(self, db_engine):
        """驗證 tables.py 的欄位與資料庫一致。"""
        inspector = inspect(db_engine)

        for table in metadata.sorted_tables:
            db_columns = {col["name"] for col in inspector.get_columns(table.name)}
            py_columns = {col.name for col in table.columns}
            assert db_columns == py_columns, f"表 {table.name} 欄位不一致"


class TestStockConstraints:
    """測試 stock 表約束。"""

    def test_stock_market_check_constraint(self, clean_db):
        """驗證 market CHECK 約束正常工作。"""
        with clean_db.begin() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO stock (stock_id, name, market) VALUES (:stock_id, :name, :market)"
                    ),
                    {"stock_id": "9999", "name": "Test", "market": "XXX"}
                )

    def test_stock_defaults(self, clean_db):
        """驗證 stock 表預設值正常。"""
        with clean_db.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO stock (stock_id, name, market) VALUES (:stock_id, :name, :market)"
                ),
                {"stock_id": "2330", "name": "台積電", "market": "TWSE"}
            )

            result = conn.execute(
                text("SELECT is_etf, is_active, created_at FROM stock WHERE stock_id = '2330'")
            ).fetchone()

            assert result[0] is False, "is_etf 預設應為 False"
            assert result[1] is True, "is_active 預設應為 True"
            assert result[2] is not None, "created_at 不應為 NULL"


class TestReversibility:
    """測試 migration 可逆性。"""

    def test_downgrade_then_upgrade(self, database_url):
        """驗證 downgrade 後再 upgrade 不會報錯。"""
        reset_database(database_url)
        # 若執行到這裡沒報錯，表示 downgrade → upgrade 可逆
        engine = __import__("sqlalchemy").create_engine(database_url)
        table_names = inspect(engine).get_table_names()
        assert "stock" in table_names
        assert "trading_calendar" in table_names
        engine.dispose()
