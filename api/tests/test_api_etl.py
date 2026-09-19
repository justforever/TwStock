"""ETL 狀態 API 測試."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from twstock_api.deps import get_db_engine
from twstock_api.main import create_app


@pytest.fixture
def client(clean_db: Engine) -> TestClient:
    """建立測試用 FastAPI 客戶端與測試資料."""
    app = create_app()
    app.dependency_overrides[get_db_engine] = lambda: clean_db

    # 插入測試資料
    with clean_db.begin() as conn:
        now = datetime.now(timezone.utc)
        # 插入 ETL 工作日誌
        conn.execute(
            text("""INSERT INTO etl_job_log (job_name, target_date, target_key, status, rows, error, started_at, finished_at)
                    VALUES (:job_name, :target_date, :target_key, :status, :rows, :error, :started_at, :finished_at)"""),
            [
                {
                    "job_name": "daily_price_twse",
                    "target_date": "2026-09-18",
                    "target_key": None,
                    "status": "success",
                    "rows": 1043,
                    "error": None,
                    "started_at": now - timedelta(hours=3),
                    "finished_at": now - timedelta(hours=3) + timedelta(minutes=7),
                },
                {
                    "job_name": "daily_price_tpex",
                    "target_date": "2026-09-18",
                    "target_key": None,
                    "status": "failed",
                    "rows": 0,
                    "error": "連線逾時",
                    "started_at": now - timedelta(hours=2),
                    "finished_at": now - timedelta(hours=2) + timedelta(minutes=5),
                },
                {
                    "job_name": "index_daily_taiex",
                    "target_date": None,
                    "target_key": "2026-09",
                    "status": "running",
                    "rows": 0,
                    "error": None,
                    "started_at": now - timedelta(hours=1),
                    "finished_at": None,
                },
            ],
        )

    return TestClient(app)


def test_get_etl_jobs(client: TestClient) -> None:
    """測試取得 ETL 工作列表."""
    response = client.get("/api/etl/jobs?limit=50")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["items"]) == 3
    # 應該依 started_at 降冪排序
    assert data["items"][0]["job_name"] == "index_daily_taiex"
    assert data["items"][1]["job_name"] == "daily_price_tpex"
    assert data["items"][2]["job_name"] == "daily_price_twse"


def test_get_etl_jobs_limit(client: TestClient) -> None:
    """測試 limit 參數."""
    response = client.get("/api/etl/jobs?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2


def test_get_etl_jobs_success_status(client: TestClient) -> None:
    """測試成功狀態的工作."""
    response = client.get("/api/etl/jobs")
    assert response.status_code == 200
    data = response.json()
    # 找成功的工作
    success_jobs = [item for item in data["items"] if item["status"] == "success"]
    assert len(success_jobs) == 1
    assert success_jobs[0]["job_name"] == "daily_price_twse"
    assert success_jobs[0]["rows"] == 1043


def test_get_etl_jobs_failed_status(client: TestClient) -> None:
    """測試失敗狀態的工作."""
    response = client.get("/api/etl/jobs")
    assert response.status_code == 200
    data = response.json()
    # 找失敗的工作
    failed_jobs = [item for item in data["items"] if item["status"] == "failed"]
    assert len(failed_jobs) == 1
    assert failed_jobs[0]["job_name"] == "daily_price_tpex"
    assert failed_jobs[0]["error"] == "連線逾時"


def test_get_etl_jobs_running_status(client: TestClient) -> None:
    """測試執行中狀態的工作."""
    response = client.get("/api/etl/jobs")
    assert response.status_code == 200
    data = response.json()
    # 找執行中的工作
    running_jobs = [item for item in data["items"] if item["status"] == "running"]
    assert len(running_jobs) == 1
    assert running_jobs[0]["job_name"] == "index_daily_taiex"
    assert running_jobs[0]["finished_at"] is None
    assert running_jobs[0]["duration_seconds"] is None


def test_get_etl_jobs_duration_seconds(client: TestClient) -> None:
    """測試耗時計算."""
    response = client.get("/api/etl/jobs")
    assert response.status_code == 200
    data = response.json()
    # success 的工作應該有耗時
    success_jobs = [item for item in data["items"] if item["status"] == "success"]
    assert success_jobs[0]["duration_seconds"] == pytest.approx(420.0, abs=1.0)  # 7 分鐘 = 420 秒


def test_get_etl_summary(client: TestClient) -> None:
    """測試 ETL 摘要."""
    response = client.get("/api/etl/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["items"]) == 3

    # 應該依 job_name 升冪排序
    job_names = [item["job_name"] for item in data["items"]]
    assert job_names == sorted(job_names)


def test_get_etl_summary_content(client: TestClient) -> None:
    """測試 ETL 摘要內容."""
    response = client.get("/api/etl/summary")
    assert response.status_code == 200
    data = response.json()

    # 找 daily_price_twse
    twse_summary = next(
        (item for item in data["items"] if item["job_name"] == "daily_price_twse"),
        None,
    )
    assert twse_summary is not None
    assert twse_summary["last_status"] == "success"
    assert twse_summary["last_rows"] == 1043
    assert twse_summary["total_runs"] == 1
    assert twse_summary["failed_last_7_days"] == 0


def test_get_etl_summary_failed_count(client: TestClient) -> None:
    """測試近 7 天失敗次數."""
    response = client.get("/api/etl/summary")
    assert response.status_code == 200
    data = response.json()

    # 找 daily_price_tpex
    tpex_summary = next(
        (item for item in data["items"] if item["job_name"] == "daily_price_tpex"),
        None,
    )
    assert tpex_summary is not None
    assert tpex_summary["last_status"] == "failed"
    # 近 7 天內有 1 次失敗
    assert tpex_summary["failed_last_7_days"] == 1
