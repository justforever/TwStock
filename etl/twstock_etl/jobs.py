"""ETL 工作函式。"""

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import Engine

from twstock_etl.errors import SourceFormatError
from twstock_etl.loaders.calendar import upsert_calendar
from twstock_etl.loaders.stock import deactivate_missing, upsert_stocks
from twstock_etl.models import CalendarDay, StockRecord
from twstock_etl.sources.isin import fetch_isin_html, parse_isin_html
from twstock_etl.sources.twse_holiday import (
    build_calendar,
    fetch_holiday_schedule,
    parse_holiday_schedule,
)

logger = logging.getLogger(__name__)

MIN_RECORDS_FOR_DEACTIVATE = 500


@dataclass(frozen=True)
class StockLoadResult:
    """個股載入結果。"""

    market: str
    records: int
    deactivated: int


@dataclass(frozen=True)
class CalendarLoadResult:
    """交易日曆載入結果。"""

    year: int
    days: int
    open_days: int
    closed_days: int


def refresh_stock_list(
    engine: Engine,
    market: str,
    *,
    html: str | None = None,
    deactivate: bool = False,
    client: httpx.Client | None = None,
) -> StockLoadResult:
    """取得（或使用傳入的）ISIN HTML，解析後在單一交易內寫入 stock。

    Args:
        engine: SQLAlchemy Engine
        market: 市場別（TWSE、TPEx）
        html: 若提供則用此 HTML，否則下載
        deactivate: 是否停用未出現的個股
        client: httpx.Client；為 None 時建立新的

    Returns:
        StockLoadResult

    Raises:
        SourceFormatError: 格式錯誤或筆數保護
    """
    if html is None:
        html = fetch_isin_html(market, client)

    records = parse_isin_html(html, market)

    # 筆數保護
    if deactivate and len(records) < MIN_RECORDS_FOR_DEACTIVATE:
        raise SourceFormatError(
            f"{market} 個股僅 {len(records)} 筆，少於 {MIN_RECORDS_FOR_DEACTIVATE}，"
            f"拒絕停用缺漏個股"
        )

    with engine.begin() as conn:
        loaded = upsert_stocks(conn, records)
        deactivated = 0
        if deactivate:
            keep_ids = {r.stock_id for r in records}
            deactivated = deactivate_missing(conn, market, keep_ids)

    logger.info(
        "刷新 %s 個股清單完成：載入 %d 筆，停用 %d 筆", market, loaded, deactivated
    )
    return StockLoadResult(market=market, records=loaded, deactivated=deactivated)


def refresh_trading_calendar(
    engine: Engine,
    year: int,
    *,
    payload: list[dict[str, str]] | None = None,
    client: httpx.Client | None = None,
) -> CalendarLoadResult:
    """取得（或使用傳入的）休市日 JSON，產生該年日曆並寫入 trading_calendar。

    Args:
        engine: SQLAlchemy Engine
        year: 年份
        payload: 若提供則用此 JSON payload，否則下載
        client: httpx.Client；為 None 時建立新的

    Returns:
        CalendarLoadResult

    Raises:
        SourceFormatError: 格式錯誤或年份不符
    """
    if payload is None:
        payload = fetch_holiday_schedule(client)

    holidays = parse_holiday_schedule(payload)
    days = build_calendar(year, holidays)

    open_days = sum(1 for d in days if d.is_open)
    closed_days = len(days) - open_days

    with engine.begin() as conn:
        upsert_calendar(conn, days)

    logger.info(
        "刷新 %d 年交易日曆完成：共 %d 天，開市 %d 天，休市 %d 天",
        year,
        len(days),
        open_days,
        closed_days,
    )
    return CalendarLoadResult(
        year=year, days=len(days), open_days=open_days, closed_days=closed_days
    )
