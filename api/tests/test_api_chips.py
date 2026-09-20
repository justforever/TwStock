"""籌碼資料 API 測試."""
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

        # 插入三大法人數據（2330）
        conn.execute(
            text("""INSERT INTO institutional_daily (stock_id, trade_date, foreign_buy, foreign_sell, foreign_net, trust_buy, trust_sell, trust_net, dealer_buy, dealer_sell, dealer_net, total_net, source)
                    VALUES (:stock_id, :trade_date, :foreign_buy, :foreign_sell, :foreign_net, :trust_buy, :trust_sell, :trust_net, :dealer_buy, :dealer_sell, :dealer_net, :total_net, :source)"""),
            [
                {"stock_id": "2330", "trade_date": date(2026, 9, 16), "foreign_buy": 25000000, "foreign_sell": 20000000, "foreign_net": 5000000, "trust_buy": 3000000, "trust_sell": 1000000, "trust_net": 2000000, "dealer_buy": 1200000, "dealer_sell": 1700000, "dealer_net": -500000, "total_net": 6500000, "source": "TWSE"},
                {"stock_id": "2330", "trade_date": date(2026, 9, 17), "foreign_buy": 28000000, "foreign_sell": 20000000, "foreign_net": 8000000, "trust_buy": 3000000, "trust_sell": 1000000, "trust_net": 2000000, "dealer_buy": 1200000, "dealer_sell": 1700000, "dealer_net": -500000, "total_net": 9500000, "source": "TWSE"},
                {"stock_id": "2330", "trade_date": date(2026, 9, 18), "foreign_buy": 30000000, "foreign_sell": 18000000, "foreign_net": 12000000, "trust_buy": 3000000, "trust_sell": 1000000, "trust_net": 2000000, "dealer_buy": 1200000, "dealer_sell": 1700000, "dealer_net": -500000, "total_net": 13500000, "source": "TWSE"},
            ],
        )

        # 插入融資融券數據（2330）
        conn.execute(
            text("""INSERT INTO margin_daily (stock_id, trade_date, margin_buy, margin_sell, margin_redeem, margin_prev_balance, margin_balance, margin_limit, short_buy, short_sell, short_redeem, short_prev_balance, short_balance, short_limit, offset_amount, sbl_sell, sbl_balance, source)
                    VALUES (:stock_id, :trade_date, :margin_buy, :margin_sell, :margin_redeem, :margin_prev_balance, :margin_balance, :margin_limit, :short_buy, :short_sell, :short_redeem, :short_prev_balance, :short_balance, :short_limit, :offset_amount, :sbl_sell, :sbl_balance, :source)"""),
            [
                {"stock_id": "2330", "trade_date": date(2026, 9, 16), "margin_buy": 1000000, "margin_sell": 800000, "margin_redeem": 0, "margin_prev_balance": 19000000, "margin_balance": 19200000, "margin_limit": None, "short_buy": 100000, "short_sell": 50000, "short_redeem": 0, "short_prev_balance": 850000, "short_balance": 900000, "short_limit": None, "offset_amount": 0, "sbl_sell": None, "sbl_balance": None, "source": "TWSE"},
                {"stock_id": "2330", "trade_date": date(2026, 9, 17), "margin_buy": 1000000, "margin_sell": 900000, "margin_redeem": 100000, "margin_prev_balance": 19200000, "margin_balance": 20000000, "margin_limit": None, "short_buy": 100000, "short_sell": 50000, "short_redeem": 0, "short_prev_balance": 900000, "short_balance": 1000000, "short_limit": None, "offset_amount": 0, "sbl_sell": None, "sbl_balance": None, "source": "TWSE"},
                {"stock_id": "2330", "trade_date": date(2026, 9, 18), "margin_buy": 1000000, "margin_sell": 900000, "margin_redeem": 100000, "margin_prev_balance": 20000000, "margin_balance": 20200000, "margin_limit": None, "short_buy": 100000, "short_sell": 50000, "short_redeem": 0, "short_prev_balance": 1000000, "short_balance": 1090000, "short_limit": None, "offset_amount": 0, "sbl_sell": 300000, "sbl_balance": 4500000, "source": "TWSE"},
            ],
        )

        # 插入外資持股數據（2330）
        conn.execute(
            text("""INSERT INTO foreign_holding (stock_id, trade_date, issued_shares, holding_shares, available_shares, holding_ratio, available_ratio, limit_ratio, source)
                    VALUES (:stock_id, :trade_date, :issued_shares, :holding_shares, :available_shares, :holding_ratio, :available_ratio, :limit_ratio, :source)"""),
            [
                {"stock_id": "2330", "trade_date": date(2026, 9, 18), "issued_shares": 25931236000, "holding_shares": 18151266320, "available_shares": 7779969680, "holding_ratio": 70.0000, "available_ratio": 30.0000, "limit_ratio": 100.0000, "source": "TWSE"},
            ],
        )

        # 插入三大法人數據（3105）
        conn.execute(
            text("""INSERT INTO institutional_daily (stock_id, trade_date, foreign_buy, foreign_sell, foreign_net, trust_buy, trust_sell, trust_net, dealer_buy, dealer_sell, dealer_net, total_net, source)
                    VALUES (:stock_id, :trade_date, :foreign_buy, :foreign_sell, :foreign_net, :trust_buy, :trust_sell, :trust_net, :dealer_buy, :dealer_sell, :dealer_net, :total_net, :source)"""),
            [
                {"stock_id": "3105", "trade_date": date(2026, 9, 18), "foreign_buy": 700000, "foreign_sell": 150000, "foreign_net": 550000, "trust_buy": 100000, "trust_sell": 50000, "trust_net": 50000, "dealer_buy": 50000, "dealer_sell": 20000, "dealer_net": 30000, "total_net": 630000, "source": "TPEx"},
            ],
        )

    return TestClient(app)


def test_法人端點三天升冪(client: TestClient):
    """測試三大法人端點回傳三天資料並升冪。"""
    response = client.get("/api/stocks/2330/institutional?from=2026-09-16&to=2026-09-18")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert [item["foreign_net"] for item in data["items"]] == [5000000, 8000000, 12000000]


def test_法人端點欄位齊全(client: TestClient):
    """測試三大法人端點回傳欄位齊全。"""
    response = client.get("/api/stocks/2330/institutional?from=2026-09-16&to=2026-09-18")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) > 0
    item = data["items"][0]
    keys = {
        "time", "foreign_buy", "foreign_sell", "foreign_net",
        "trust_buy", "trust_sell", "trust_net",
        "dealer_buy", "dealer_sell", "dealer_net", "total_net"
    }
    assert set(item.keys()) == keys


def test_融資券端點_margin_ratio(client: TestClient):
    """測試融資券端點 margin_ratio 計算。"""
    response = client.get("/api/stocks/2330/margin?from=2026-09-16&to=2026-09-18")
    assert response.status_code == 200
    data = response.json()
    last_item = data["items"][-1]
    assert last_item["margin_balance"] == 20200000
    assert last_item["short_balance"] == 1090000
    assert last_item["margin_ratio"] == 5.396


def test_margin_balance_為零時_margin_ratio_是_None(client: TestClient):
    """測試 margin_balance 為零時 margin_ratio 是 None。"""
    engine = client.app.dependency_overrides[get_db_engine]()
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO margin_daily (stock_id, trade_date, margin_buy, margin_sell, margin_redeem, margin_prev_balance, margin_balance, margin_limit, short_buy, short_sell, short_redeem, short_prev_balance, short_balance, short_limit, offset_amount, source)
                    VALUES (:stock_id, :trade_date, :margin_buy, :margin_sell, :margin_redeem, :margin_prev_balance, :margin_balance, :margin_limit, :short_buy, :short_sell, :short_redeem, :short_prev_balance, :short_balance, :short_limit, :offset_amount, :source)"""),
            {"stock_id": "2330", "trade_date": date(2026, 9, 19), "margin_buy": 0, "margin_sell": 0, "margin_redeem": 0, "margin_prev_balance": 0, "margin_balance": 0, "margin_limit": None, "short_buy": 0, "short_sell": 0, "short_redeem": 0, "short_prev_balance": 0, "short_balance": 0, "short_limit": None, "offset_amount": 0, "source": "TWSE"}
        )

    response = client.get("/api/stocks/2330/margin?from=2026-09-19&to=2026-09-19")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) > 0
    assert data["items"][0]["margin_ratio"] is None


def test_sbl_沒資料時是_None(client: TestClient):
    """測試第一筆 sbl_sell 沒資料時是 None。"""
    response = client.get("/api/stocks/2330/margin?from=2026-09-16&to=2026-09-18")
    assert response.status_code == 200
    data = response.json()
    first_item = data["items"][0]
    assert first_item["sbl_sell"] is None
    assert first_item["sbl_balance"] is None
    # 最後一筆應該有 sbl_sell
    last_item = data["items"][-1]
    assert last_item["sbl_sell"] == 300000
    assert last_item["sbl_balance"] == 4500000


def test_外資持股端點(client: TestClient):
    """測試外資持股端點。"""
    response = client.get("/api/stocks/2330/foreign-holding")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    item = data["items"][0]
    assert item["holding_shares"] == 18151266320
    assert item["holding_ratio"] == 70.0
    assert item["available_ratio"] == 30.0


def test_from_大於_to_回_422(client: TestClient):
    """測試 from 大於 to 回 422。"""
    response = client.get("/api/stocks/2330/institutional?from=2026-09-20&to=2026-09-16")
    assert response.status_code == 422


def test_個股不存在回_404(client: TestClient):
    """測試個股不存在回 404。"""
    response = client.get("/api/stocks/9999/institutional")
    assert response.status_code == 404


def test_區間內無資料回_200_count_0(client: TestClient):
    """測試區間內無資料回 200、count 0、items 空。"""
    response = client.get("/api/stocks/2330/institutional?from=2020-01-01&to=2020-01-31")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["items"] == []


def test_limit_取最新的幾筆(client: TestClient):
    """測試 limit 取最新的幾筆。"""
    # 先插入 5 天的數據
    engine = client.app.dependency_overrides[get_db_engine]()
    with engine.begin() as conn:
        for i in range(1, 6):
            conn.execute(
                text("""INSERT INTO institutional_daily (stock_id, trade_date, foreign_buy, foreign_sell, foreign_net, trust_buy, trust_sell, trust_net, dealer_buy, dealer_sell, dealer_net, total_net, source)
                        VALUES (:stock_id, :trade_date, :foreign_buy, :foreign_sell, :foreign_net, :trust_buy, :trust_sell, :trust_net, :dealer_buy, :dealer_sell, :dealer_net, :total_net, :source)"""),
                {"stock_id": "3105", "trade_date": date(2026, 9, 18 + i), "foreign_buy": 1000000 * i, "foreign_sell": 500000 * i, "foreign_net": 500000 * i, "trust_buy": 100000, "trust_sell": 50000, "trust_net": 50000, "dealer_buy": 50000, "dealer_sell": 20000, "dealer_net": 30000, "total_net": 580000 * i, "source": "TPEx"}
            )

    response = client.get("/api/stocks/3105/institutional?limit=2")
    assert response.status_code == 200
    data = response.json()
    # 應該只回最新的 2 筆
    assert data["count"] == 2
    # 應該升冪（新的最後）
    assert data["items"][-1]["time"] == "2026-09-23"
