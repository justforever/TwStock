"""backfill CLI 子指令測試。"""

import sys
from datetime import date
from pathlib import Path
from io import StringIO

import pytest

from twstock_etl.backfill import BackfillAborted, BackfillSummary
from twstock_etl.cli import main


def test_backfill_price_呼叫_backfill_prices_並帶對參數(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試 backfill price 子指令會正確呼叫 backfill_prices。"""
    captured_args = {}

    def fake_backfill_prices(*args, **kwargs):
        captured_args["args"] = args
        captured_args["kwargs"] = kwargs
        return BackfillSummary(total=1, done=1, skipped=0, failed=0, rows=10)

    def fake_engine():
        return object()

    monkeypatch.setattr("twstock_etl.cli.get_engine", fake_engine)
    monkeypatch.setattr("twstock_etl.cli.backfill_prices", fake_backfill_prices)

    result = main(
        [
            "backfill",
            "price",
            "--market",
            "TWSE",
            "--from",
            "2026-09-16",
            "--to",
            "2026-09-18",
            "--sleep",
            "0",
            "--source-dir",
            "etl/tests/fixtures",
        ]
    )

    assert result == 0
    engine, market, start, end, options = captured_args["args"]
    assert market == "TWSE"
    assert start == date(2026, 9, 16)
    assert end == date(2026, 9, 18)
    assert options.sleep_seconds == 0.0
    assert options.source_dir == Path("etl/tests/fixtures")


def test_backfill_有失敗回_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試回補有失敗時回傳 1。"""

    def fake_backfill_prices(*args, **kwargs):
        return BackfillSummary(total=1, done=0, skipped=0, failed=1, rows=0)

    monkeypatch.setattr("twstock_etl.cli.get_engine", lambda: object())
    monkeypatch.setattr("twstock_etl.cli.backfill_prices", fake_backfill_prices)

    result = main(
        [
            "backfill",
            "price",
            "--market",
            "TWSE",
            "--from",
            "2026-09-16",
            "--to",
            "2026-09-18",
        ]
    )

    assert result == 1


def test_backfill_被中斷回_130(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試回補被中斷時回傳 130。"""

    def fake_backfill_prices(*args, **kwargs):
        summary = BackfillSummary(total=1, done=0, skipped=0, failed=0, rows=0)
        summary.interrupted_at = "2026-09-17"
        return summary

    monkeypatch.setattr("twstock_etl.cli.get_engine", lambda: object())
    monkeypatch.setattr("twstock_etl.cli.backfill_prices", fake_backfill_prices)

    result = main(
        [
            "backfill",
            "price",
            "--market",
            "TWSE",
            "--from",
            "2026-09-16",
            "--to",
            "2026-09-18",
        ]
    )

    assert result == 130


def test_backfill_超過失敗上限回_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試回補超過失敗上限時回傳 2。"""

    def fake_backfill_prices(*args, **kwargs):
        raise BackfillAborted("失敗次數超過 10，中止回補")

    monkeypatch.setattr("twstock_etl.cli.get_engine", lambda: object())
    monkeypatch.setattr("twstock_etl.cli.backfill_prices", fake_backfill_prices)

    result = main(
        [
            "backfill",
            "price",
            "--market",
            "TWSE",
            "--from",
            "2026-09-16",
            "--to",
            "2026-09-18",
        ]
    )

    assert result == 2


def test_backfill_index_子指令參數是年月字串(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試 backfill index 子指令年月參數是字串。"""
    captured_args = {}

    def fake_backfill_index(*args, **kwargs):
        captured_args["args"] = args
        return BackfillSummary(total=1, done=1, skipped=0, failed=0, rows=10)

    monkeypatch.setattr("twstock_etl.cli.get_engine", lambda: object())
    monkeypatch.setattr("twstock_etl.cli.backfill_index", fake_backfill_index)

    result = main(
        [
            "backfill",
            "index",
            "--from",
            "2026-09",
            "--to",
            "2026-09",
            "--sleep",
            "0",
        ]
    )

    assert result == 0
    engine, start, end, options = captured_args["args"]
    assert start == "2026-09"
    assert end == "2026-09"
