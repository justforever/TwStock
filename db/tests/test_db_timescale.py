"""TimescaleDB 功能測試。"""
import os

import pytest
from sqlalchemy import text

from twstock_db.config import get_database_url
from twstock_db.timescale import (
    create_hypertable_if_available,
    timescaledb_available,
    timescaledb_installed,
)


class TestTimescaleValidation:
    """測試 TimescaleDB 參數驗證。"""

    def test_invalid_identifier_raises(self, db_engine):
        """驗證無效的識別字會拋出 ValueError。"""
        with db_engine.connect() as conn:
            with pytest.raises(ValueError):
                create_hypertable_if_available(conn, "stock; DROP", "trade_date")


class TestTimescaleAvailability:
    """測試 TimescaleDB 可用性檢測。"""

    def test_available_matches_catalog(self, db_engine):
        """驗證 timescaledb_available 結果與 pg_available_extensions 一致。"""
        with db_engine.connect() as conn:
            available = timescaledb_available(conn)

            # 直接查詢 pg_available_extensions
            result = conn.execute(
                text("SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'")
            )
            expected_available = result.scalar() is not None

            assert available == expected_available


class TestHypertableWithoutTimescale:
    """測試沒有 TimescaleDB 時的行為。"""

    def test_hypertable_noop_without_timescale(self, db_engine):
        """驗證未安裝 TimescaleDB 時 create_hypertable_if_available 回傳 False。"""
        with db_engine.connect() as conn:
            # 如果已安裝，跳過此測試
            if timescaledb_installed(conn):
                pytest.skip("TimescaleDB 已安裝，測試跳過")

            # 未安裝時應回傳 False
            result = create_hypertable_if_available(conn, "trading_calendar", "trade_date")
            assert result is False


class TestConfigMissing:
    """測試設定缺失的情況。"""

    def test_get_database_url_missing(self, monkeypatch):
        """驗證未設定 DATABASE_URL 時拋出 RuntimeError。"""
        monkeypatch.delenv("DATABASE_URL", raising=False)

        with pytest.raises(RuntimeError, match="環境變數 DATABASE_URL 未設定"):
            get_database_url()
