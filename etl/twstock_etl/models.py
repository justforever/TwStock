"""ETL 資料模型。"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

Market = Literal["TWSE", "TPEx", "ESB"]


@dataclass(frozen=True)
class StockRecord:
    """個股記錄。"""

    stock_id: str  # 例 "2330"
    name: str  # 例 "台積電"
    market: Market
    industry: str | None  # 產業別中文；空字串要轉成 None
    listed_date: date | None
    is_etf: bool
    isin_code: str | None
    cfi_code: str | None


@dataclass(frozen=True)
class Holiday:
    """休市日紀錄。"""

    holiday_date: date
    name: str  # 例 "農曆除夕及春節"
    description: str  # 可為空字串
    is_trading_day: bool  # 「開始交易日」「最後交易日」這類條目為 True


@dataclass(frozen=True)
class CalendarDay:
    """交易日曆日紀錄。"""

    trade_date: date
    is_open: bool
    note: str | None
