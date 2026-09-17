from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from twstock_api.deps import get_db_engine
from twstock_api.main import create_app


@pytest.fixture
def client(clean_db: Engine) -> TestClient:
    """建立測試用 FastAPI 客戶端."""
    app = create_app()
    app.dependency_overrides[get_db_engine] = lambda: clean_db

    # 插入測試資料
    with clean_db.begin() as conn:
        conn.execute(
            text("""INSERT INTO stock (stock_id, name, market, industry, listed_date, is_etf, is_active)
                    VALUES (:stock_id, :name, :market, :industry, :listed_date, :is_etf, :is_active)"""),
            [
                {"stock_id": "2330", "name": "台積電", "market": "TWSE", "industry": "半導體業", "listed_date": date(1994, 9, 5), "is_etf": False, "is_active": True},
                {"stock_id": "2317", "name": "鴻海", "market": "TWSE", "industry": "其他電子業", "listed_date": date(1991, 6, 18), "is_etf": False, "is_active": True},
                {"stock_id": "2834", "name": "臺企銀", "market": "TWSE", "industry": "金融保險業", "listed_date": date(1998, 1, 13), "is_etf": False, "is_active": True},
                {"stock_id": "0050", "name": "元大台灣50", "market": "TWSE", "industry": None, "listed_date": date(2003, 6, 30), "is_etf": True, "is_active": True},
                {"stock_id": "00679B", "name": "元大美債20年", "market": "TPEx", "industry": None, "listed_date": date(2017, 1, 17), "is_etf": True, "is_active": True},
                {"stock_id": "5347", "name": "世界", "market": "TPEx", "industry": "半導體業", "listed_date": date(1998, 3, 30), "is_etf": False, "is_active": True},
                {"stock_id": "9999", "name": "已下市測試", "market": "TWSE", "industry": None, "listed_date": None, "is_etf": False, "is_active": False},
            ],
        )

    return TestClient(app)


def test_search_exact_code(client: TestClient) -> None:
    """測試完全相符代號."""
    response = client.get("/api/stocks?q=2330")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "2330"
    assert data["count"] == 1
    assert data["items"][0]["stock_id"] == "2330"
    assert data["items"][0]["name"] == "台積電"
    assert data["items"][0]["market"] == "TWSE"
    assert data["items"][0]["industry"] == "半導體業"
    assert data["items"][0]["listed_date"] == "1994-09-05"
    assert data["items"][0]["is_etf"] is False


def test_search_code_prefix(client: TestClient) -> None:
    """測試代號前綴."""
    response = client.get("/api/stocks?q=23")
    assert response.status_code == 200
    data = response.json()
    assert [item["stock_id"] for item in data["items"]] == ["2317", "2330"]


def test_search_name_contains_simple(client: TestClient) -> None:
    """測試名稱包含（台積）."""
    response = client.get("/api/stocks?q=台積")
    assert response.status_code == 200
    data = response.json()
    assert [item["stock_id"] for item in data["items"]] == ["2330"]


def test_search_name_with_taiwan_char(client: TestClient) -> None:
    """測試臺→台 轉換（臺積）."""
    response = client.get("/api/stocks?q=臺積")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "臺積"
    assert [item["stock_id"] for item in data["items"]] == ["2330"]


def test_search_name_with_taiwan_char_2(client: TestClient) -> None:
    """測試臺→台 轉換（台企）."""
    response = client.get("/api/stocks?q=台企")
    assert response.status_code == 200
    data = response.json()
    assert [item["stock_id"] for item in data["items"]] == ["2834"]


def test_search_case_insensitive(client: TestClient) -> None:
    """測試大小寫不敏感."""
    response = client.get("/api/stocks?q=00679b")
    assert response.status_code == 200
    data = response.json()
    assert [item["stock_id"] for item in data["items"]] == ["00679B"]


def test_search_name_prefix_ordering(client: TestClient) -> None:
    """測試名稱前綴排序（元大）."""
    response = client.get("/api/stocks?q=元大")
    assert response.status_code == 200
    data = response.json()
    assert [item["stock_id"] for item in data["items"]] == ["0050", "00679B"]


def test_search_name_contains_no_code_prefix(client: TestClient) -> None:
    """測試名稱包含但代號不符."""
    response = client.get("/api/stocks?q=50")
    assert response.status_code == 200
    data = response.json()
    assert [item["stock_id"] for item in data["items"]] == ["0050"]


def test_search_inactive_stock(client: TestClient) -> None:
    """測試不回傳已下市個股."""
    response = client.get("/api/stocks?q=已下市")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["items"] == []


def test_search_escape_like_percent(client: TestClient) -> None:
    """測試 LIKE 跳脫 %."""
    response = client.get("/api/stocks?q=%25")  # %25 = %
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0


def test_search_with_limit(client: TestClient) -> None:
    """測試 limit 參數."""
    response = client.get("/api/stocks?q=2&limit=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1


def test_search_missing_q(client: TestClient) -> None:
    """測試缺少 q 參數."""
    response = client.get("/api/stocks")
    assert response.status_code == 422


def test_search_empty_q_after_strip(client: TestClient) -> None:
    """測試 q 為空白."""
    response = client.get("/api/stocks?q=%20%20")  # 空格
    assert response.status_code == 422


def test_search_invalid_limit(client: TestClient) -> None:
    """測試無效 limit."""
    response = client.get("/api/stocks?q=2330&limit=0")
    assert response.status_code == 422

    response = client.get("/api/stocks?q=2330&limit=101")
    assert response.status_code == 422


def test_search_q_too_long(client: TestClient) -> None:
    """測試 q 超過長度限制."""
    response = client.get("/api/stocks?q=" + "a" * 51)
    assert response.status_code == 422
