"""ETL 資料模型。"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
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


@dataclass(frozen=True)
class PriceRecord:
    """個股日成交紀錄（未還原原始價）。"""

    stock_id: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    change: Decimal | None  # 含正負號；無法判斷符號時為 None
    volume: int  # 成交股數
    turnover: Decimal  # 成交金額（元）
    transactions: int  # 成交筆數
    source: str  # "TWSE" 或 "TPEx"


@dataclass(frozen=True)
class IndexRecord:
    """指數日 K 紀錄。"""

    index_id: str  # M1 只有 "TAIEX"
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None = None  # M1 一律 None


@dataclass(frozen=True)
class AdjFactorRecord:
    """除權息還原係數紀錄。"""

    stock_id: str
    ex_date: date
    factor: Decimal  # 除權息參考價 ÷ 除權息前收盤價，8 位小數
    prev_close: Decimal | None
    reference_price: Decimal | None
    kind: str | None  # 除息 / 除權 / 除權息
    source: str = "TWSE"


@dataclass(frozen=True)
class InstitutionalRecord:
    """三大法人買賣超紀錄（單位：股）。"""

    stock_id: str
    trade_date: date
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
    source: str  # "TWSE" 或 "TPEx"


@dataclass(frozen=True)
class MarginRecord:
    """融資融券紀錄（單位：股）。"""

    stock_id: str
    trade_date: date
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
    source: str


@dataclass(frozen=True)
class SblRecord:
    """借券賣出紀錄（單位：股），寫進 margin_daily 的 sbl_* 欄位。"""

    stock_id: str
    trade_date: date
    sbl_sell: int
    sbl_balance: int
    source: str = "TWSE"


@dataclass(frozen=True)
class ForeignHoldingRecord:
    """外資持股紀錄。"""

    stock_id: str
    trade_date: date
    issued_shares: int | None
    holding_shares: int
    available_shares: int | None
    holding_ratio: Decimal | None
    available_ratio: Decimal | None
    limit_ratio: Decimal | None
    source: str = "TWSE"


@dataclass(frozen=True)
class ShareholdingRecord:
    """集保股權分散單一級距紀錄。"""

    stock_id: str
    week_date: date
    level: int  # 1–17
    holders: int
    shares: int
    ratio: Decimal
