"""Hypertable 雙簽名測試。"""
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from twstock_db.timescale import (
    create_hypertable_if_available,
    timescaledb_installed,
)


class TestCreateHypertableSignatures:
    """測試 create_hypertable_if_available 的雙簽名機制。"""

    def test_create_hypertable_uses_by_range_first(self, monkeypatch):
        """驗證優先使用 by_range() 簽名。"""
        conn = MagicMock()
        monkeypatch.setattr("twstock_db.timescale.timescaledb_installed", lambda c: True)

        result = create_hypertable_if_available(conn, "daily_price", "trade_date", "1 month")

        assert result is True
        assert conn.execute.call_count >= 1
        # 檢查第一個 execute 呼叫包含 by_range
        first_call_sql = str(conn.execute.call_args_list[0][0][0])
        assert "by_range" in first_call_sql
        # 檢查參數
        second_arg = conn.execute.call_args_list[0][0][1]
        assert second_arg == {"table": "daily_price", "time_column": "trade_date", "interval": "1 month"}

    def test_create_hypertable_falls_back_to_legacy(self, monkeypatch):
        """驗證 by_range() 失敗時退回舊簽名。"""
        conn = MagicMock()
        monkeypatch.setattr("twstock_db.timescale.timescaledb_installed", lambda c: True)

        # 第一次呼叫 by_range 拋 DBAPIError，第二次呼叫舊簽名成功
        conn.execute.side_effect = [
            DBAPIError("stmt", {}, Exception("function by_range does not exist")),
            None  # 舊簽名成功
        ]

        result = create_hypertable_if_available(conn, "daily_price", "trade_date", "1 month")

        assert result is True
        assert conn.execute.call_count == 2
        # 檢查第二個 execute 呼叫包含 chunk_time_interval
        second_call_sql = str(conn.execute.call_args_list[1][0][0])
        assert "chunk_time_interval" in second_call_sql

    def test_create_hypertable_skipped_without_extension(self, db_engine):
        """驗證未安裝 TimescaleDB 時跳過建立。"""
        with db_engine.connect() as conn:
            if timescaledb_installed(conn):
                pytest.skip("此 PostgreSQL 已安裝 TimescaleDB")

            result = create_hypertable_if_available(conn, "daily_price", "trade_date")

            assert result is False

            # 驗證表仍可正常 INSERT
            conn.execute(
                text(
                    "INSERT INTO daily_price (stock_id, trade_date, close, source) VALUES (:stock_id, :trade_date, :close, :source)"
                ),
                {"stock_id": "2330", "trade_date": "2026-09-18", "close": 1000.00, "source": "TWSE"}
            )

    def test_hypertables_registered_when_timescale_installed(self, db_engine):
        """驗證 TimescaleDB 安裝時 hypertable 已建立。"""
        with db_engine.connect() as conn:
            if not timescaledb_installed(conn):
                pytest.skip("此 PostgreSQL 未安裝 TimescaleDB，hypertable 實跑留待使用者本機驗證")

            # 查詢 timescaledb_information.hypertables
            result = conn.execute(
                text("SELECT hypertable_name FROM timescaledb_information.hypertables ORDER BY hypertable_name")
            ).fetchall()

            hypertable_names = {row[0] for row in result}
            assert "daily_price" in hypertable_names
            assert "index_daily" in hypertable_names
