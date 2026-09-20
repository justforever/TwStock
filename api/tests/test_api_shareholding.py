"""集保股權分散 API 測試."""
from datetime import date

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
        # 插入個股
        conn.execute(
            text("""INSERT INTO stock (stock_id, name, market, industry, listed_date, is_etf, is_active)
                    VALUES (:stock_id, :name, :market, :industry, :listed_date, :is_etf, :is_active)"""),
            [
                {"stock_id": "2330", "name": "台積電", "market": "TWSE", "industry": "半導體業", "listed_date": date(1994, 9, 5), "is_etf": False, "is_active": True},
            ],
        )

        # 插入集保股權分散數據（2330）
        # 根據 fixture：1=5%, 2=10%, 3=5%, 12=10%, 13=10%, 14=10%, 15=50%
        # 大戶（12-15）= 80%, 散戶（1-4）= 20%, level 16 = 100%（不計入）
        conn.execute(
            text("""INSERT INTO shareholding_dist (stock_id, week_date, level, holders, shares, ratio)
                    VALUES (:stock_id, :week_date, :level, :holders, :shares, :ratio)"""),
            [
                {"stock_id": "2330", "week_date": date(2026, 9, 18), "level": 1, "holders": 600000, "shares": 50000000, "ratio": 5.0000},
                {"stock_id": "2330", "week_date": date(2026, 9, 18), "level": 2, "holders": 350000, "shares": 100000000, "ratio": 10.0000},
                {"stock_id": "2330", "week_date": date(2026, 9, 18), "level": 3, "holders": 40000, "shares": 50000000, "ratio": 5.0000},
                {"stock_id": "2330", "week_date": date(2026, 9, 18), "level": 12, "holders": 5000, "shares": 100000000, "ratio": 10.0000},
                {"stock_id": "2330", "week_date": date(2026, 9, 18), "level": 13, "holders": 2000, "shares": 100000000, "ratio": 10.0000},
                {"stock_id": "2330", "week_date": date(2026, 9, 18), "level": 14, "holders": 1500, "shares": 100000000, "ratio": 10.0000},
                {"stock_id": "2330", "week_date": date(2026, 9, 18), "level": 15, "holders": 1500, "shares": 500000000, "ratio": 50.0000},
                {"stock_id": "2330", "week_date": date(2026, 9, 18), "level": 16, "holders": 1000000, "shares": 1000000000, "ratio": 100.0000},
            ],
        )

    return TestClient(app)


def test_單週分組與大戶比例(client: TestClient):
    """測試集保端點單週分組與大戶比例。"""
    response = client.get("/api/stocks/2330/shareholding")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    item = data["items"][0]
    assert item["big_holder_ratio"] == 80.0
    assert item["retail_ratio"] == 20.0
    assert item["total_holders"] == 1000000  # level 16
    assert item["total_shares"] == 1000000000  # level 16
    assert len(item["levels"]) == 7  # level 1-15 中有 8 列，但只有 7 個不同的 level


def test_沒有_level_16_時_total_用_1_到_15_加總(client: TestClient):
    """測試沒有 level 16 時 total 用 level 1-15 加總。"""
    # 插入新的週沒有 level 16
    engine = client.app.dependency_overrides[get_db_engine]()
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO shareholding_dist (stock_id, week_date, level, holders, shares, ratio)
                    VALUES (:stock_id, :week_date, :level, :holders, :shares, :ratio)"""),
            [
                {"stock_id": "2330", "week_date": date(2026, 10, 2), "level": 1, "holders": 100000, "shares": 10000000, "ratio": 1.0},
                {"stock_id": "2330", "week_date": date(2026, 10, 2), "level": 2, "holders": 200000, "shares": 20000000, "ratio": 2.0},
            ],
        )

    response = client.get("/api/stocks/2330/shareholding?from=2026-10-02&to=2026-10-02")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    item = data["items"][0]
    # 沒有 level 16，所以用 level 1-15 加總
    assert item["total_holders"] == 300000  # 100000 + 200000
    assert item["total_shares"] == 30000000  # 10000000 + 20000000


def test_limit_取最新幾週(client: TestClient):
    """測試 limit 取最新幾週。"""
    # 插入三週的數據
    engine = client.app.dependency_overrides[get_db_engine]()
    with engine.begin() as conn:
        for week_offset in [1, 2]:
            week_date = date(2026, 10, 2 + week_offset * 7)
            conn.execute(
                text("""INSERT INTO shareholding_dist (stock_id, week_date, level, holders, shares, ratio)
                        VALUES (:stock_id, :week_date, :level, :holders, :shares, :ratio)"""),
                [
                    {"stock_id": "2330", "week_date": week_date, "level": 1, "holders": 100000, "shares": 10000000, "ratio": 1.0},
                    {"stock_id": "2330", "week_date": week_date, "level": 16, "holders": 1000000, "shares": 1000000000, "ratio": 100.0},
                ]
            )

    response = client.get("/api/stocks/2330/shareholding?limit=2")
    assert response.status_code == 200
    data = response.json()
    # 應該回最新的 2 週
    assert data["count"] == 2
    # 應該升冪（最舊的在前，最新的在後）
    assert data["items"][0]["week"] < data["items"][1]["week"]


def test_level_16_17_不出現在_levels(client: TestClient):
    """測試 level 16 17 不出現在 levels 中。"""
    response = client.get("/api/stocks/2330/shareholding")
    assert response.status_code == 200
    data = response.json()
    item = data["items"][0]
    levels = [level["level"] for level in item["levels"]]
    # 不應該包含 16 或更高
    assert 16 not in levels
    assert 17 not in levels
    # 應該只有 1-15 中實際有的
    assert all(1 <= level <= 15 for level in levels)
