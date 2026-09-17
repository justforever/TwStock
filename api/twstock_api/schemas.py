from datetime import date
from typing import Literal

from pydantic import BaseModel


class StockItem(BaseModel):
    """個股項目."""
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx", "ESB"]
    industry: str | None
    listed_date: date | None
    is_etf: bool


class StockSearchResponse(BaseModel):
    """個股搜尋回應."""
    query: str
    count: int
    items: list[StockItem]


class HealthResponse(BaseModel):
    """健康檢查回應."""
    status: Literal["ok", "error"]
    db: Literal["ok", "unreachable"]
