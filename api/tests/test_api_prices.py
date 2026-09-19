"""個股價格 API 測試."""
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
                {"stock_id": "3105", "name": "穩懋", "market": "TPEx", "industry": "半導體業", "listed_date": date(1997, 9, 5), "is_etf": False, "is_active": True},
            ],
        )

        # 插入日 K（2330）
        conn.execute(
            text("""INSERT INTO daily_price (stock_id, trade_date, open, high, low, close, change, volume, turnover, transactions, source)
                    VALUES (:stock_id, :trade_date, :open, :high, :low, :close, :change, :volume, :turnover, :transactions, :source)"""),
            [
                {
                    "stock_id": "2330",
                    "trade_date": date(2026, 9, 16),
                    "open": 985.05,
                    "high": 994.95,
                    "low": 980.1,
                    "close": 1000.0,
                    "change": 4.95,
                    "volume": 25000000,
                    "turnover": 25000000000,
                    "transactions": 30000,
                    "source": "TWSE",
                },
                {
                    "stock_id": "2330",
                    "trade_date": date(2026, 9, 17),
                    "open": 992.0,
                    "high": 998.0,
                    "low": 988.0,
                    "close": 995.0,
                    "change": -5.0,
                    "volume": 20000000,
                    "turnover": 19900000000,
                    "transactions": 25000,
                    "source": "TWSE",
                },
                {
                    "stock_id": "2330",
                    "trade_date": date(2026, 9, 18),
                    "open": 996.0,
                    "high": 1010.0,
                    "low": 995.0,
                    "close": 1008.0,
                    "change": 13.0,
                    "volume": 30000000,
                    "turnover": 30000000000,
                    "transactions": 35000,
                    "source": "TWSE",
                },
            ],
        )

        # 插入日 K（3105）
        conn.execute(
            text("""INSERT INTO daily_price (stock_id, trade_date, open, high, low, close, change, volume, turnover, transactions, source)
                    VALUES (:stock_id, :trade_date, :open, :high, :low, :close, :change, :volume, :turnover, :transactions, :source)"""),
            [
                {
                    "stock_id": "3105",
                    "trade_date": date(2026, 9, 16),
                    "open": 348.0,
                    "high": 352.0,
                    "low": 347.0,
                    "close": 350.0,
                    "change": 2.0,
                    "volume": 2800000,
                    "turnover": 980000000,
                    "transactions": 2300,
                    "source": "TPEx",
                },
                {
                    "stock_id": "3105",
                    "trade_date": date(2026, 9, 17),
                    "open": 351.0,
                    "high": 353.0,
                    "low": 348.0,
                    "close": 352.0,
                    "change": 2.0,
                    "volume": 2800000,
                    "turnover": 980000000,
                    "transactions": 2300,
                    "source": "TPEx",
                },
                {
                    "stock_id": "3105",
                    "trade_date": date(2026, 9, 18),
                    "open": 351.0,
                    "high": 353.0,
                    "low": 348.0,
                    "close": 349.0,
                    "change": -3.0,
                    "volume": 2800000,
                    "turnover": 980000000,
                    "transactions": 2300,
                    "source": "TPEx",
                },
            ],
        )

        # 插入除權息係數
        conn.execute(
            text("""INSERT INTO adj_factor (stock_id, ex_date, factor, prev_close, reference_price, kind, source)
                    VALUES (:stock_id, :ex_date, :factor, :prev_close, :reference_price, :kind, :source)"""),
            [
                {
                    "stock_id": "2330",
                    "ex_date": date(2026, 9, 17),
                    "factor": 0.99,
                    "prev_close": 1000.0,
                    "reference_price": 990.0,
                    "kind": "除息",
                    "source": "TWSE",
                },
            ],
        )

    return TestClient(app)


def test_get_prices_basic(client: TestClient) -> None:
    """測試基本價格查詢."""
    response = client.get("/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18")
    assert response.status_code == 200
    data = response.json()
    assert data["stock_id"] == "2330"
    assert data["name"] == "台積電"
    assert data["count"] == 3
    assert data["adjusted"] is False
    assert data["items"][0]["close"] == 1000.0
    assert data["items"][0]["time"] == "2026-09-16"
    assert data["items"][2]["close"] == 1008.0


def test_get_prices_adjusted(client: TestClient) -> None:
    """測試還原價查詢."""
    response = client.get("/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18&adj=true")
    assert response.status_code == 200
    data = response.json()
    assert data["adjusted"] is True
    # 09-16 的收盤價應該乘以 0.99
    assert data["items"][0]["close"] == 990.0
    # 09-17 和 09-18 不受影響
    assert data["items"][1]["close"] == 995.0
    assert data["items"][2]["close"] == 1008.0


def test_get_prices_adjusted_open_high_low(client: TestClient) -> None:
    """測試還原價的開高低."""
    response = client.get("/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18&adj=true")
    assert response.status_code == 200
    data = response.json()
    # 09-16 的所有價格都應該乘以 0.99
    assert data["items"][0]["open"] == pytest.approx(985.05 * 0.99, abs=0.01)
    assert data["items"][0]["high"] == pytest.approx(994.95 * 0.99, abs=0.01)
    assert data["items"][0]["low"] == pytest.approx(980.1 * 0.99, abs=0.01)


def test_get_prices_volume_not_adjusted(client: TestClient) -> None:
    """測試還原價不調整成交量."""
    response = client.get("/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18&adj=true")
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["volume"] == 25000000


def test_get_prices_not_found(client: TestClient) -> None:
    """測試查無個股."""
    response = client.get("/api/stocks/9999/prices")
    assert response.status_code == 404
    assert "查無此個股" in response.json()["detail"]


def test_get_prices_from_after_to(client: TestClient) -> None:
    """測試 from > to 的錯誤."""
    response = client.get("/api/stocks/2330/prices?from=2026-09-20&to=2026-09-18")
    assert response.status_code == 422
    assert "from 不可晚於 to" in response.json()["detail"]


def test_get_prices_no_data_in_range(client: TestClient) -> None:
    """測試區間內無資料."""
    response = client.get("/api/stocks/2330/prices?from=2026-10-01&to=2026-10-31")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["items"] == []


def test_get_prices_limit(client: TestClient) -> None:
    """測試 limit 參數."""
    response = client.get("/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18&limit=1")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    # 應該回傳最新的一筆（09-18）
    assert data["items"][0]["time"] == "2026-09-18"
    assert data["items"][0]["close"] == 1008.0


def test_get_stock_detail(client: TestClient) -> None:
    """測試取得個股詳細資訊."""
    response = client.get("/api/stocks/2330")
    assert response.status_code == 200
    data = response.json()
    assert data["stock_id"] == "2330"
    assert data["name"] == "台積電"
    assert data["market"] == "TWSE"
    assert data["industry"] == "半導體業"
    assert data["listed_date"] == "1994-09-05"
    assert data["is_etf"] is False
    assert data["is_active"] is True
    assert data["latest"]["close"] == 1008.0


def test_get_stock_detail_not_found(client: TestClient) -> None:
    """測試取得不存在的個股."""
    response = client.get("/api/stocks/9999")
    assert response.status_code == 404
    assert "查無此個股" in response.json()["detail"]


def test_get_tpex_prices(client: TestClient) -> None:
    """測試上櫃個股價格."""
    response = client.get("/api/stocks/3105/prices?from=2026-09-16&to=2026-09-18")
    assert response.status_code == 200
    data = response.json()
    assert data["stock_id"] == "3105"
    assert data["market"] == "TPEx"
    assert data["count"] == 3
    assert data["items"][-1]["close"] == 349.0
