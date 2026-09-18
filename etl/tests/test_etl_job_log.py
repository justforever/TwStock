"""ETL 工作日誌 loader 測試。"""

from datetime import date

import pytest
from sqlalchemy import select

from twstock_db.tables import etl_job_log
from twstock_etl.loaders.job_log import JobSkipped, has_successful_run, job_run, latest_run


def test_job_run_success(clean_db):
    """測試 job_run 成功路徑。"""
    with job_run(clean_db, "daily_price_twse", target_date=date(2026, 9, 18)) as run:
        run.rows = 42

    # 驗證 DB
    with clean_db.begin() as conn:
        record = conn.execute(select(etl_job_log)).first()

    assert record.job_name == "daily_price_twse"
    assert record.target_date == date(2026, 9, 18)
    assert record.status == "success"
    assert record.rows == 42
    assert record.finished_at is not None
    assert record.error is None


def test_job_run_failed(clean_db):
    """測試 job_run 失敗路徑。"""
    with pytest.raises(RuntimeError, match="測試錯誤"):
        with job_run(clean_db, "daily_price_twse", target_date=date(2026, 9, 18)) as run:
            run.rows = 10
            raise RuntimeError("測試錯誤")

    # 驗證 DB
    with clean_db.begin() as conn:
        record = conn.execute(select(etl_job_log)).first()

    assert record.status == "failed"
    assert "測試錯誤" in record.error
    assert record.finished_at is not None
    # 失敗時 rows 不應該更新
    assert record.rows == 0


def test_job_run_skipped(clean_db):
    """測試 job_run 跳過路徑。"""
    # JobSkipped 不應該往外拋
    with job_run(clean_db, "daily_price_twse", target_date=date(2026, 9, 18)) as run:
        run.skip("非開市日")

    # 驗證 DB
    with clean_db.begin() as conn:
        record = conn.execute(select(etl_job_log)).first()

    assert record.status == "skipped"
    assert record.error == "非開市日"
    assert record.finished_at is not None


def test_job_run_error_truncated(clean_db):
    """測試 job_run 錯誤訊息截斷。"""
    long_message = "x" * 3000

    with pytest.raises(RuntimeError):
        with job_run(clean_db, "test_job") as run:
            raise RuntimeError(long_message)

    # 驗證 DB 中錯誤訊息被截斷
    with clean_db.begin() as conn:
        record = conn.execute(select(etl_job_log)).first()

    assert record.status == "failed"
    assert len(record.error) == 2000


def test_has_successful_run_success(clean_db):
    """測試 has_successful_run 查詢成功狀態。"""
    with job_run(clean_db, "daily_price_twse", target_date=date(2026, 9, 18)) as run:
        run.rows = 100

    with clean_db.begin() as conn:
        exists = has_successful_run(
            conn, "daily_price_twse", target_date=date(2026, 9, 18)
        )

    assert exists is True


def test_has_successful_run_skipped(clean_db):
    """測試 has_successful_run 查詢跳過狀態。"""
    with job_run(clean_db, "daily_price_twse", target_date=date(2026, 9, 18)) as run:
        run.skip("非開市日")

    with clean_db.begin() as conn:
        exists = has_successful_run(
            conn, "daily_price_twse", target_date=date(2026, 9, 18)
        )

    assert exists is True


def test_has_successful_run_failed(clean_db):
    """測試 has_successful_run 查詢失敗狀態。"""
    with pytest.raises(RuntimeError):
        with job_run(clean_db, "daily_price_twse", target_date=date(2026, 9, 18)) as run:
            raise RuntimeError("測試錯誤")

    with clean_db.begin() as conn:
        exists = has_successful_run(
            conn, "daily_price_twse", target_date=date(2026, 9, 18)
        )

    assert exists is False


def test_has_successful_run_not_found(clean_db):
    """測試 has_successful_run 查詢不存在的 job。"""
    with clean_db.begin() as conn:
        exists = has_successful_run(
            conn, "nonexistent_job", target_date=date(2026, 9, 18)
        )

    assert exists is False


def test_has_successful_run_different_targets(clean_db):
    """測試 has_successful_run 不同目標的隔離。"""
    with job_run(clean_db, "daily_price_twse", target_date=date(2026, 9, 18)) as run:
        run.rows = 100

    with clean_db.begin() as conn:
        exists_18 = has_successful_run(
            conn, "daily_price_twse", target_date=date(2026, 9, 18)
        )
        exists_19 = has_successful_run(
            conn, "daily_price_twse", target_date=date(2026, 9, 19)
        )

    assert exists_18 is True
    assert exists_19 is False


def test_latest_run_found(clean_db):
    """測試 latest_run 找到最新紀錄。"""
    with job_run(clean_db, "daily_price_twse", target_date=date(2026, 9, 16)) as run:
        run.rows = 100

    with job_run(clean_db, "daily_price_twse", target_date=date(2026, 9, 17)) as run:
        run.rows = 200

    with job_run(clean_db, "daily_price_twse", target_date=date(2026, 9, 18)) as run:
        run.rows = 300

    with clean_db.begin() as conn:
        record = latest_run(conn, "daily_price_twse")

    assert record is not None
    assert record["target_date"] == date(2026, 9, 18)
    assert record["rows"] == 300
    assert record["status"] == "success"


def test_latest_run_not_found(clean_db):
    """測試 latest_run 找不到紀錄。"""
    with clean_db.begin() as conn:
        record = latest_run(conn, "nonexistent_job")

    assert record is None
