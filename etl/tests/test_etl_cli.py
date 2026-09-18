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


def test_load_price_cli(clean_db, monkeypatch, capsys):
    """測試 load-price CLI 指令。"""
    # 設定資料庫環境變數
    import os
    database_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    if database_url:
        monkeypatch.setenv("DATABASE_URL", database_url)
        get_engine.cache_clear()

    # 先載入個股清單
    main(["load-stocks", "--market", "TWSE", "--file", _fixture_path("isin_twse_strmode2.html")])

    # 執行 load-price
    result = main([
        "load-price",
        "--market", "TWSE",
        "--file", _fixture_path("TWSE_price_20260918.json"),
        "--date", "2026-09-18",
        "--no-calendar-check"
    ])

    assert result == 0
    out, err = capsys.readouterr()
    assert "rows=4" in out

    get_engine.cache_clear()


def test_load_index_cli(clean_db, monkeypatch, capsys):
    """測試 load-index CLI 指令。"""
    import os
    database_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    if database_url:
        monkeypatch.setenv("DATABASE_URL", database_url)
        get_engine.cache_clear()

    # 執行 load-index
    result = main([
        "load-index",
        "--year", "2026",
        "--month", "9",
        "--file", _fixture_path("TAIEX_index_202609.json")
    ])

    assert result == 0
    out, err = capsys.readouterr()
    assert "rows=3" in out

    get_engine.cache_clear()


def test_load_index_cli_force(clean_db, monkeypatch, capsys):
    """測試 load-index CLI 指令 force 參數。"""
    import os
    database_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    if database_url:
        monkeypatch.setenv("DATABASE_URL", database_url)
        get_engine.cache_clear()

    # 第一次執行
    result1 = main([
        "load-index",
        "--year", "2026",
        "--month", "9",
        "--file", _fixture_path("TAIEX_index_202609.json")
    ])
    assert result1 == 0
    out1, err1 = capsys.readouterr()
    assert "rows=3" in out1

    # 第二次執行用 force
    result2 = main([
        "load-index",
        "--year", "2026",
        "--month", "9",
        "--force",
        "--file", _fixture_path("TAIEX_index_202609.json")
    ])
    assert result2 == 0
    out2, err2 = capsys.readouterr()
    assert "rows=3" in out2

    get_engine.cache_clear()


def test_load_exright_cli(clean_db, monkeypatch, capsys):
    """測試 load-exright CLI 指令。"""
    import os
    database_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    if database_url:
        monkeypatch.setenv("DATABASE_URL", database_url)
        get_engine.cache_clear()

    # 先載入個股清單
    main(["load-stocks", "--market", "TWSE", "--file", _fixture_path("isin_twse_strmode2.html")])

    # 執行 load-exright
    result = main([
        "load-exright",
        "--from", "2026-09-01",
        "--to", "2026-09-30",
        "--file", _fixture_path("exright_20260901_20260930.json")
    ])

    assert result == 0
    out, err = capsys.readouterr()
    assert "rows=2" in out

    get_engine.cache_clear()


def test_load_exright_cli_skip(clean_db, monkeypatch, capsys):
    """測試 load-exright CLI 指令 skip 情況。"""
    import os
    database_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    if database_url:
        monkeypatch.setenv("DATABASE_URL", database_url)
        get_engine.cache_clear()

    # 先載入個股清單
    main(["load-stocks", "--market", "TWSE", "--file", _fixture_path("isin_twse_strmode2.html")])

    # 第一次執行
    result1 = main([
        "load-exright",
        "--from", "2026-09-01",
        "--to", "2026-09-30",
        "--file", _fixture_path("exright_20260901_20260930.json")
    ])
    assert result1 == 0
    out1, err1 = capsys.readouterr()
    assert "rows=2" in out1

    # 第二次執行應該 skip
    result2 = main([
        "load-exright",
        "--from", "2026-09-01",
        "--to", "2026-09-30",
        "--file", _fixture_path("exright_20260901_20260930.json")
    ])
    assert result2 == 0
    out2, err2 = capsys.readouterr()
    assert "skipped" in out2
    assert "已完成，略過" in out2

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
