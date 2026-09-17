import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from twstock_api.deps import get_db_engine
from twstock_api.main import create_app


def test_health_ok(clean_db: Engine) -> None:
    """測試健康檢查成功."""
    app = create_app()
    app.dependency_overrides[get_db_engine] = lambda: clean_db
    client = TestClient(app)

    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"


def test_health_db_unreachable() -> None:
    """測試 DB 連線失敗."""
    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")

    app = create_app()
    app.dependency_overrides[get_db_engine] = lambda: engine
    client = TestClient(app)

    response = client.get("/api/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"
    assert data["db"] == "unreachable"
