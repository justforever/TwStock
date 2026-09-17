"""ETL CLI 測試。"""

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, func, select

from twstock_db.engine import get_engine
from twstock_db.tables import stock
from twstock_etl.cli import main


def _fixture_path(filename: str) -> str:
    """取得 fixture 路徑。"""
    return str(Path(__file__).parent / "fixtures" / filename)


def test_load_stocks_twse(clean_db, monkeypatch, capsys):
    """測試載入 TWSE 個股。"""
    # 設定 DATABASE_URL 和清除快取
    db_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_engine.cache_clear()

    result = main(
        [
            "load-stocks",
            "--market",
            "TWSE",
            "--file",
            _fixture_path("isin_twse_strmode2.html"),
        ]
    )

    assert result == 0
    out, err = capsys.readouterr()
    assert "loaded market=TWSE records=9 deactivated=0" in out

    get_engine.cache_clear()


def test_load_stocks_tpex(clean_db, monkeypatch, capsys):
    """測試載入 TPEx 個股。"""
    db_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_engine.cache_clear()

    result = main(
        [
            "load-stocks",
            "--market",
            "TPEx",
            "--file",
            _fixture_path("isin_tpex_strmode4.html"),
        ]
    )

    assert result == 0
    out, err = capsys.readouterr()
    assert "loaded market=TPEx records=8 deactivated=0" in out

    get_engine.cache_clear()


def test_load_calendar(clean_db, monkeypatch, capsys):
    """測試載入交易日曆。"""
    db_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_engine.cache_clear()

    result = main(
        [
            "load-calendar",
            "--year",
            "2026",
            "--file",
            _fixture_path("twse_holiday_schedule_2026.json"),
        ]
    )

    assert result == 0
    out, err = capsys.readouterr()
    assert "loaded year=2026 days=365 open=250 closed=115" in out

    get_engine.cache_clear()


def test_load_calendar_wrong_year(clean_db, monkeypatch, capsys):
    """測試載入錯誤年份的日曆。"""
    db_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_engine.cache_clear()

    result = main(
        [
            "load-calendar",
            "--year",
            "2025",
            "--file",
            _fixture_path("twse_holiday_schedule_2026.json"),
        ]
    )

    assert result == 1
    out, err = capsys.readouterr()
    assert "error:" in err

    get_engine.cache_clear()


def test_load_stocks_nonexistent_file(clean_db, monkeypatch, capsys):
    """測試載入不存在的檔案。"""
    db_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_engine.cache_clear()

    result = main(
        ["load-stocks", "--market", "TWSE", "--file", "/nonexistent.html"]
    )

    assert result == 1
    out, err = capsys.readouterr()
    assert "error:" in err

    get_engine.cache_clear()


def test_load_stocks_deactivate_guard(clean_db, monkeypatch, capsys):
    """測試停用時的筆數保護。"""
    db_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_engine.cache_clear()

    result = main(
        [
            "load-stocks",
            "--market",
            "TWSE",
            "--file",
            _fixture_path("isin_twse_strmode2.html"),
            "--deactivate-missing",
        ]
    )

    assert result == 1
    out, err = capsys.readouterr()
    assert "error:" in err

    get_engine.cache_clear()


def test_missing_database_url(monkeypatch, capsys):
    """測試未設定 DATABASE_URL。"""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_engine.cache_clear()

    result = main(["load-stocks", "--market", "TWSE", "--file", "/dev/null"])

    assert result == 1
    out, err = capsys.readouterr()
    assert "error:" in err
    assert "DATABASE_URL" in err

    get_engine.cache_clear()
