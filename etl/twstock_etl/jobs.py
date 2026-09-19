"""ETL 工作函式。"""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import Connection, Engine, select

from twstock_db.tables import trading_calendar
from twstock_etl.errors import SourceFormatError
from twstock_etl.loaders.calendar import insert_calendar_if_absent, upsert_calendar
from twstock_etl.loaders.job_log import has_successful_run, job_run
from twstock_etl.loaders.price import (
    index_trade_dates,
    upsert_adj_factors,
    upsert_daily_prices,
    upsert_index_daily,
)
from twstock_etl.loaders.stock import (
    count_active_stocks,
    deactivate_missing,
    upsert_stocks,
)
from twstock_etl.models import CalendarDay, StockRecord
from twstock_etl.sources.isin import fetch_isin_html, parse_isin_html
from twstock_etl.sources.tpex_price import fetch_tpex_daily, parse_tpex_daily
from twstock_etl.sources.twse_exright import fetch_exright, parse_exright
from twstock_etl.sources.twse_holiday import (
    build_calendar,
    fetch_holiday_schedule,
    parse_holiday_schedule,
)
from twstock_etl.sources.twse_index import fetch_taiex_month, parse_taiex_month
from twstock_etl.sources.twse_price import fetch_twse_daily, parse_twse_daily

logger = logging.getLogger(__name__)

TAIPEI = ZoneInfo("Asia/Taipei")
DEACTIVATE_MIN_RATIO = 0.7
DEACTIVATE_MIN_ABSOLUTE = 50


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

    with engine.begin() as conn:
        if deactivate:
            previous = count_active_stocks(conn, market)
            if previous > 0 and len(records) < previous * DEACTIVATE_MIN_RATIO:
                raise SourceFormatError(
                    f"{market} 本次解析 {len(records)} 筆，低於前次有效筆數 {previous} 的 "
                    f"{DEACTIVATE_MIN_RATIO:.0%}（門檻 {previous * DEACTIVATE_MIN_RATIO:.0f} 筆），拒絕停用缺漏個股"
                )
            if previous == 0 and len(records) < DEACTIVATE_MIN_ABSOLUTE:
                raise SourceFormatError(
                    f"{market} 本次解析 {len(records)} 筆，少於初次建庫下限 "
                    f"{DEACTIVATE_MIN_ABSOLUTE} 筆，拒絕停用缺漏個股"
                )
        loaded = upsert_stocks(conn, records)
        deactivated = deactivate_missing(conn, market, {r.stock_id for r in records}) if deactivate else 0

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


def refresh_calendar_with_next_year(
    engine: Engine, year: int, *, client: httpx.Client | None = None
) -> list[CalendarLoadResult]:
    """刷新 year 與 year+1 的交易日曆。

    year+1 的資料在官方尚未公布時（build_calendar 拋 SourceFormatError）
    記 INFO log 並略過，不視為失敗。回傳成功的結果清單（長度 1 或 2）。
    只下載一次 payload，兩個年度共用。

    Args:
        engine: SQLAlchemy Engine
        year: 起始年份
        client: httpx.Client；為 None 時建立新的

    Returns:
        CalendarLoadResult 清單
    """
    payload = fetch_holiday_schedule(client)
    holidays = parse_holiday_schedule(payload)
    results = []

    for y in [year, year + 1]:
        try:
            days = build_calendar(y, holidays)
            open_days = sum(1 for d in days if d.is_open)
            closed_days = len(days) - open_days

            with engine.begin() as conn:
                upsert_calendar(conn, days)

            result = CalendarLoadResult(
                year=y, days=len(days), open_days=open_days, closed_days=closed_days
            )
            results.append(result)
            logger.info(
                "刷新 %d 年交易日曆完成：共 %d 天，開市 %d 天，休市 %d 天",
                y,
                len(days),
                open_days,
                closed_days,
            )
        except SourceFormatError:
            if y == year + 1:
                logger.info("年份 %d 的交易日曆官方尚未公布，略過", y)
            else:
                raise

    return results


def rebuild_calendar_from_index(
    engine: Engine, year: int, *, index_id: str = "TAIEX", overwrite: bool = False
) -> CalendarLoadResult:
    """用 index_daily 已回補的指數交易日反推某歷史年度的交易日曆。

    Args:
        engine: SQLAlchemy Engine
        year: 年份
        index_id: 指數 ID，預設 TAIEX
        overwrite: 是否覆蓋官方來源已寫入的 note

    Returns:
        CalendarLoadResult

    Raises:
        SourceFormatError: 指數資料不足
    """
    with engine.begin() as conn:
        dates = index_trade_dates(conn, index_id, year)

    if len(dates) < 200:
        raise SourceFormatError(
            f"{year} 年 {index_id} 只有 {len(dates)} 個交易日，"
            f"不足以推算日曆，請先回補指數"
        )

    # 產生該年每一天
    all_days = []
    current_date = date(year, 1, 1)
    end_date = date(year, 12, 31)

    while current_date <= end_date:
        if current_date in dates:
            day = CalendarDay(trade_date=current_date, is_open=True, note=None)
        else:
            day = CalendarDay(
                trade_date=current_date, is_open=False, note="未開市（由指數回補推得）"
            )
        all_days.append(day)
        current_date = date(
            current_date.year, current_date.month, current_date.day
        ) + timedelta(days=1)

    # 寫入
    open_days = sum(1 for d in all_days if d.is_open)
    closed_days = len(all_days) - open_days

    with engine.begin() as conn:
        if overwrite:
            upsert_calendar(conn, all_days)
        else:
            insert_calendar_if_absent(conn, all_days)

    logger.info(
        "從 %s 指數反推 %d 年日曆完成：共 %d 天，開市 %d 天，休市 %d 天",
        index_id,
        year,
        len(all_days),
        open_days,
        closed_days,
    )
    return CalendarLoadResult(
        year=year, days=len(all_days), open_days=open_days, closed_days=closed_days
    )


def is_trading_day(conn: Connection, trade_date: date) -> bool | None:
    """查 trading_calendar；True=開市、False=休市、None=日曆沒有這一天。

    Args:
        conn: 資料庫連線
        trade_date: 交易日

    Returns:
        True/False/None
    """
    stmt = select(trading_calendar.c.is_open).where(
        trading_calendar.c.trade_date == trade_date
    )
    result = conn.execute(stmt).scalar()
    return result


@dataclass(frozen=True)
class PriceJobResult:
    """單一交易日的日 K 載入結果。"""

    market: str
    trade_date: date
    rows: int
    skipped_unknown: int
    skip_reason: str | None = None


@dataclass(frozen=True)
class IndexJobResult:
    """指數月份載入結果。"""

    year: int
    month: int
    rows: int
    skip_reason: str | None = None


@dataclass(frozen=True)
class AdjFactorJobResult:
    """除權息載入結果。"""

    start: date
    end: date
    rows: int
    skip_reason: str | None = None


def load_daily_price(
    engine: Engine,
    market: str,
    trade_date: date,
    *,
    payload: dict | None = None,
    client: httpx.Client | None = None,
    check_calendar: bool = True,
    force: bool = False,
) -> PriceJobResult:
    """抓（或用傳入的）單一交易日行情並寫入 daily_price，全程記 etl_job_log。

    Args:
        engine: SQLAlchemy Engine
        market: 市場別（TWSE、TPEx）
        trade_date: 交易日
        payload: 若提供則用此 JSON payload，否則下載
        client: httpx.Client；為 None 時建立新的
        check_calendar: 是否檢查交易日曆
        force: 是否強制重抓

    Returns:
        PriceJobResult；被略過時 rows=0、skipped_unknown=0、skip_reason 為略過原因

    Raises:
        ValueError: market 不是 TWSE / TPEx
    """
    if market not in ("TWSE", "TPEx"):
        raise ValueError(f"市場別錯誤：{market}")

    job_name = f"daily_price_{market.lower()}"
    rows = 0
    skipped_unknown = 0

    with job_run(engine, job_name, target_date=trade_date) as run:
        with engine.begin() as conn:
            # 檢查是否已完成
            if not force and has_successful_run(
                conn, job_name, target_date=trade_date
            ):
                run.skip("已完成，略過")

            # 檢查交易日曆
            if check_calendar:
                is_open = is_trading_day(conn, trade_date)
                if is_open is False:
                    run.skip("非開市日")
                elif is_open is None:
                    logger.warning("日曆缺少 %s", trade_date)

        # 抓或讀取資料
        if payload is None:
            if market == "TWSE":
                payload = fetch_twse_daily(trade_date, client)
            else:
                payload = fetch_tpex_daily(trade_date, client)

        # 解析
        if market == "TWSE":
            records = parse_twse_daily(payload, trade_date)
        else:
            records = parse_tpex_daily(payload, trade_date)

        # 寫入
        with engine.begin() as conn:
            upsert_result = upsert_daily_prices(conn, records)
        rows = upsert_result.written
        skipped_unknown = upsert_result.skipped_unknown
        run.rows = rows

    return PriceJobResult(
        market=market,
        trade_date=trade_date,
        rows=rows,
        skipped_unknown=skipped_unknown,
        skip_reason=run.note,
    )


def load_index_month(
    engine: Engine,
    year: int,
    month: int,
    *,
    payload: dict | None = None,
    client: httpx.Client | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> IndexJobResult:
    """抓某年某月的 TAIEX 指數歷史並寫入 index_daily，回傳結果。

    當月（now 或台北時間今天所在的月）一律視為未完成，不 skip。

    Args:
        engine: SQLAlchemy Engine
        year: 年份
        month: 月份
        payload: 若提供則用此 JSON payload，否則下載
        client: httpx.Client；為 None 時建立新的
        force: 是否強制重抓
        now: 判斷「當月」的基準時間；為 None 時用 datetime.now(TAIPEI)（見 D-026）

    Returns:
        IndexJobResult；被略過時 rows=0、skip_reason 為略過原因
    """
    target_key = f"{year:04d}-{month:02d}"
    job_name = "index_daily_taiex"
    rows = 0

    with job_run(engine, job_name, target_key=target_key) as run:
        # 檢查是否為當月（基準時間可注入，不直接在分支裡呼叫 datetime.now）
        ref = now or datetime.now(TAIPEI)
        is_current_month = ref.year == year and ref.month == month

        # 檢查是否已完成（當月一律跳過此檢查）
        with engine.begin() as conn:
            if (
                not force
                and not is_current_month
                and has_successful_run(conn, job_name, target_key=target_key)
            ):
                run.skip("已完成，略過")

        # 抓或讀取資料
        if payload is None:
            payload = fetch_taiex_month(year, month, client)

        # 解析
        records = parse_taiex_month(payload, year, month)

        # 寫入
        with engine.begin() as conn:
            rows = upsert_index_daily(conn, records)
        run.rows = rows

    return IndexJobResult(year=year, month=month, rows=rows, skip_reason=run.note)


def load_adj_factors(
    engine: Engine,
    start: date,
    end: date,
    *,
    payload: dict | None = None,
    client: httpx.Client | None = None,
    force: bool = False,
) -> AdjFactorJobResult:
    """抓某區間的除權除息計算結果並寫入 adj_factor，回傳結果。

    Args:
        engine: SQLAlchemy Engine
        start: 起始日期（含）
        end: 結束日期（含）
        payload: 若提供則用此 JSON payload，否則下載
        client: httpx.Client；為 None 時建立新的
        force: 是否強制重抓

    Returns:
        AdjFactorJobResult；被略過時 rows=0、skip_reason 為略過原因

    Raises:
        ValueError: 區間長度超過 31 天
    """
    delta = (end - start).days
    if delta > 31:
        raise ValueError("區間長度不可超過 31 天（官方端點限制）")

    target_key = f"{start:%Y%m%d}-{end:%Y%m%d}"
    job_name = "adj_factor_twse"
    rows = 0

    with job_run(engine, job_name, target_key=target_key) as run:
        with engine.begin() as conn:
            if not force and has_successful_run(conn, job_name, target_key=target_key):
                run.skip("已完成，略過")

        # 抓或讀取資料
        if payload is None:
            payload = fetch_exright(start, end, client)

        # 解析
        records = parse_exright(payload)

        # 寫入
        with engine.begin() as conn:
            upsert_result = upsert_adj_factors(conn, records)
        rows = upsert_result.written
        run.rows = rows

    return AdjFactorJobResult(start=start, end=end, rows=rows, skip_reason=run.note)
