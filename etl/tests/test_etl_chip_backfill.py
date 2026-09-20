"""籌碼 backfill 測試。"""

from datetime import date
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from twstock_db.tables import stock as stock_table
from twstock_etl.backfill import backfill_chip, BackfillOptions, BackfillSummary
from twstock_etl.jobs import ChipJobResult
from twstock_etl.models import InstitutionalRecord, CalendarDay
from twstock_etl.loaders.calendar import upsert_calendar


def test_backfill_chip_basic(clean_db, tmp_path):
    """測試基本回補功能。"""
    # 先建立股票與交易日曆
    with clean_db.begin() as conn:
        conn.execute(
            stock_table.insert().values({
                "stock_id": "2330",
                "name": "台積電",
                "market": "TWSE",
                "industry": "半導體",
                "listed_date": date(1994, 9, 5),
                "is_etf": False,
                "isin_code": "TW0002330008",
                "cfi_code": "ESVUFR",
            })
        )
        upsert_calendar(conn, [CalendarDay(date(2026, 9, 21), True, None)])

    with patch("twstock_etl.backfill.load_chip_daily") as mock_load:
        mock_load.return_value = ChipJobResult(
            kind="institutional",
            market="TWSE",
            trade_date=date(2026, 9, 21),
            rows=1,
            skipped_unknown=0,
            skip_reason=None,
        )

        options = BackfillOptions(
            sleep_seconds=0,
            max_failures=10,
            force=False,
            source_dir=None,
            dry_run=False,
        )

        result = backfill_chip(
            clean_db,
            "institutional",
            "TWSE",
            date(2026, 9, 21),
            date(2026, 9, 21),
            options,
        )

    assert isinstance(result, BackfillSummary)
    assert result.done == 1
    assert result.skipped == 0
    assert result.failed == 0
    assert result.rows == 1


def test_backfill_chip_invalid_combo(clean_db):
    """測試無效的 kind/market 組合會立即失敗。"""
    options = BackfillOptions(
        sleep_seconds=0,
        max_failures=10,
        force=False,
        source_dir=None,
        dry_run=False,
    )

    try:
        backfill_chip(
            clean_db,
            "sbl",
            "TPEx",  # sbl 在 TPEx 不存在
            date(2026, 9, 21),
            date(2026, 9, 21),
            options,
        )
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "沒有這個籌碼來源" in str(e)


def test_backfill_chip_dry_run(clean_db):
    """測試 dry_run 模式不實際載入。"""
    with clean_db.begin() as conn:
        conn.execute(
            stock_table.insert().values({
                "stock_id": "2330",
                "name": "台積電",
                "market": "TWSE",
                "industry": "半導體",
                "listed_date": date(1994, 9, 5),
                "is_etf": False,
                "isin_code": "TW0002330008",
                "cfi_code": "ESVUFR",
            })
        )
        upsert_calendar(conn, [CalendarDay(date(2026, 9, 21), True, None)])

    with patch("twstock_etl.backfill.load_chip_daily") as mock_load:
        options = BackfillOptions(
            sleep_seconds=0,
            max_failures=10,
            force=False,
            source_dir=None,
            dry_run=True,
        )

        result = backfill_chip(
            clean_db,
            "institutional",
            "TWSE",
            date(2026, 9, 21),
            date(2026, 9, 21),
            options,
        )

    # dry_run 模式下不應該呼叫 load_chip_daily
    mock_load.assert_not_called()
    assert result.done == 1  # dry_run 也計入 done，但不會實際執行 load_chip_daily
    assert result.rows == 0  # 因為沒有實際執行，所以 rows 為 0


def test_backfill_chip_error_handling(clean_db):
    """測試錯誤處理。"""
    with clean_db.begin() as conn:
        conn.execute(
            stock_table.insert().values({
                "stock_id": "2330",
                "name": "台積電",
                "market": "TWSE",
                "industry": "半導體",
                "listed_date": date(1994, 9, 5),
                "is_etf": False,
                "isin_code": "TW0002330008",
                "cfi_code": "ESVUFR",
            })
        )
        upsert_calendar(conn, [CalendarDay(date(2026, 9, 21), True, None)])

    with patch("twstock_etl.backfill.load_chip_daily") as mock_load:
        mock_load.side_effect = Exception("Network error")

        options = BackfillOptions(
            sleep_seconds=0,
            max_failures=10,
            force=False,
            source_dir=None,
            dry_run=False,
        )

        result = backfill_chip(
            clean_db,
            "institutional",
            "TWSE",
            date(2026, 9, 21),
            date(2026, 9, 21),
            options,
        )

    assert result.failed == 1
    assert result.done == 0
