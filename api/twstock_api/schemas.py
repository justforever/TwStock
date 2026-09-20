from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class PriceBar(BaseModel):
    """一根日 K。"""
    time: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    change: float | None
    volume: int
    turnover: float
    transactions: int


class IndexBar(BaseModel):
    """一根指數日 K。"""
    time: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None


class PriceResponse(BaseModel):
    """股價查詢回應."""
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx", "ESB"]
    adjusted: bool
    from_: date = Field(alias="from")
    to: date
    count: int
    items: list[PriceBar]
    model_config = ConfigDict(populate_by_name=True)


class IndexResponse(BaseModel):
    """指數查詢回應."""
    index_id: str
    name: str
    from_: date = Field(alias="from")
    to: date
    count: int
    items: list[IndexBar]
    model_config = ConfigDict(populate_by_name=True)


class StockDetail(BaseModel):
    """個股詳細資訊。"""
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx", "ESB"]
    industry: str | None
    listed_date: date | None
    is_etf: bool
    is_active: bool
    latest: PriceBar | None


class EtlJobRun(BaseModel):
    """ETL 工作執行紀錄。"""
    job_id: int
    job_name: str
    target_date: date | None
    target_key: str | None
    status: Literal["running", "success", "failed", "skipped"]
    rows: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None


class EtlJobSummaryItem(BaseModel):
    """ETL 工作摘要項目。"""
    job_name: str
    last_status: Literal["running", "success", "failed", "skipped"]
    last_target_date: date | None
    last_target_key: str | None
    last_rows: int
    last_started_at: datetime
    last_finished_at: datetime | None
    failed_last_7_days: int
    total_runs: int


class EtlJobListResponse(BaseModel):
    """ETL 工作列表回應。"""
    count: int
    items: list[EtlJobRun]


class EtlSummaryResponse(BaseModel):
    """ETL 摘要回應。"""
    count: int
    items: list[EtlJobSummaryItem]


class InstitutionalBar(BaseModel):
    """一天的三大法人買賣超（股）。"""
    time: date
    foreign_buy: int
    foreign_sell: int
    foreign_net: int
    trust_buy: int
    trust_sell: int
    trust_net: int
    dealer_buy: int
    dealer_sell: int
    dealer_net: int
    total_net: int


class MarginBar(BaseModel):
    """一天的融資融券與借券（股）。"""
    time: date
    margin_buy: int
    margin_sell: int
    margin_redeem: int
    margin_prev_balance: int
    margin_balance: int
    margin_limit: int | None
    short_buy: int
    short_sell: int
    short_redeem: int
    short_prev_balance: int
    short_balance: int
    short_limit: int | None
    offset_amount: int
    sbl_sell: int | None
    sbl_balance: int | None
    margin_ratio: float | None


class ForeignHoldingBar(BaseModel):
    """一天的外資持股。"""
    time: date
    issued_shares: int | None
    holding_shares: int
    available_shares: int | None
    holding_ratio: float | None
    available_ratio: float | None
    limit_ratio: float | None


class ShareholdingLevel(BaseModel):
    """集保股權分散的一個級距。"""
    level: int
    holders: int
    shares: int
    ratio: float


class ShareholdingWeek(BaseModel):
    """集保股權分散的一週。"""
    week: date
    total_holders: int
    total_shares: int
    big_holder_ratio: float
    retail_ratio: float
    levels: list[ShareholdingLevel]


class InstitutionalResponse(BaseModel):
    """三大法人買賣超查詢回應."""
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx", "ESB"]
    from_: date = Field(alias="from")
    to: date
    count: int
    items: list[InstitutionalBar]
    model_config = ConfigDict(populate_by_name=True)


class MarginResponse(BaseModel):
    """融資融券查詢回應."""
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx", "ESB"]
    from_: date = Field(alias="from")
    to: date
    count: int
    items: list[MarginBar]
    model_config = ConfigDict(populate_by_name=True)


class ForeignHoldingResponse(BaseModel):
    """外資持股查詢回應."""
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx", "ESB"]
    from_: date = Field(alias="from")
    to: date
    count: int
    items: list[ForeignHoldingBar]
    model_config = ConfigDict(populate_by_name=True)


class ShareholdingResponse(BaseModel):
    """集保股權分散查詢回應."""
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx", "ESB"]
    from_: date = Field(alias="from")
    to: date
    count: int
    items: list[ShareholdingWeek]
    model_config = ConfigDict(populate_by_name=True)
