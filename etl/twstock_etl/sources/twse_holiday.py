"""TWSE 休市日 parser 與交易日曆產生。"""

import logging
from datetime import date, timedelta
from typing import Sequence

import httpx

from twstock_etl.dates import parse_tw_date
from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import CalendarDay, Holiday

logger = logging.getLogger(__name__)

HOLIDAY_URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
TRADING_DAY_KEYWORDS = ("開始交易", "最後交易")


def fetch_holiday_schedule(client: httpx.Client | None = None) -> list[dict[str, str]]:
    """下載 TWSE 休市日 JSON。

    Args:
        client: httpx.Client 實例；為 None 時建立新的

    Returns:
        JSON 陣列內容（dict 清單）

    Raises:
        SourceFormatError: 回傳不是 list
    """
    if client is None:
        client = default_client()
        should_close = True
    else:
        should_close = False

    try:
        response = get_with_retry(client, HOLIDAY_URL)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            raise SourceFormatError(
                f"TWSE 休市日 API 回傳非陣列：{type(data).__name__}"
            )

        return data
    finally:
        if should_close:
            client.close()


def parse_holiday_schedule(payload: list[dict[str, str]]) -> list[Holiday]:
    """把 OpenAPI JSON 轉成 Holiday 清單。

    Args:
        payload: JSON 陣列內容

    Returns:
        Holiday 清單

    Raises:
        SourceFormatError: 缺必要鍵或日期無效
    """
    holidays: list[Holiday] = []

    for item in payload:
        if "Name" not in item or "Date" not in item:
            raise SourceFormatError(
                f"休市日資料缺必要鍵：{item}"
            )

        name = item["Name"]
        date_str = item["Date"]
        description = item.get("Description", "")

        try:
            holiday_date = parse_tw_date(date_str)
        except ValueError as e:
            raise SourceFormatError(f"日期解析失敗：{item}") from e

        is_trading_day = any(
            k in name or k in description for k in TRADING_DAY_KEYWORDS
        )

        holiday = Holiday(
            holiday_date=holiday_date,
            name=name,
            description=description,
            is_trading_day=is_trading_day,
        )
        holidays.append(holiday)

    return holidays


def build_calendar(year: int, holidays: Sequence[Holiday]) -> list[CalendarDay]:
    """產生該年 1/1～12/31 每一天的 CalendarDay。

    規則：
    1. holidays 中 holiday_date.year != year 的忽略
    2. 過濾後若沒有任何一筆 → raise SourceFormatError
    3. 對每一天：
       - 該日有任一 is_trading_day=False 的 Holiday → is_open=False，note=第一筆此類的 name（截到 64 字）
       - 否則若 d.weekday() >= 5 → is_open=False，note="週末"
       - 否則 → is_open=True，note=None

    Args:
        year: 年份
        holidays: Holiday 清單

    Returns:
        CalendarDay 清單（長度 365 或 366）

    Raises:
        SourceFormatError: 過濾後無該年度資料
    """
    # 過濾該年度的假日
    year_holidays = [h for h in holidays if h.holiday_date.year == year]

    if not year_holidays:
        raise SourceFormatError(f"休市日資料不含 {year} 年")

    # 判斷是否閏年
    is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    end_day = 366 if is_leap else 365

    calendar: list[CalendarDay] = []
    current = date(year, 1, 1)
    end = date(year, 12, 31)

    while current <= end:
        # 找該日的假日條目
        day_holidays = [h for h in year_holidays if h.holiday_date == current]

        # 檢查是否有休市的假日條目
        rest_holidays = [h for h in day_holidays if not h.is_trading_day]

        if rest_holidays:
            # 有休市的假日條目，取第一筆
            note = rest_holidays[0].name[:64]
            cal_day = CalendarDay(
                trade_date=current,
                is_open=False,
                note=note,
            )
        elif current.weekday() >= 5:
            # 週末
            cal_day = CalendarDay(
                trade_date=current,
                is_open=False,
                note="週末",
            )
        else:
            # 平日開市
            cal_day = CalendarDay(
                trade_date=current,
                is_open=True,
                note=None,
            )

        calendar.append(cal_day)
        current += timedelta(days=1)

    return calendar
