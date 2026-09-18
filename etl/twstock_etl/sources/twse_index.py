"""加權指數 parser。"""

import logging
from datetime import date
from decimal import Decimal

import httpx

from twstock_etl.dates import parse_tw_date
from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import IndexRecord
from twstock_etl.numbers import parse_decimal
from twstock_etl.sources.report import extract_table

logger = logging.getLogger(__name__)

TAIEX_HIST_URL = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST"
TAIEX_INDEX_ID = "TAIEX"
TAIEX_FIELDS = ("日期", "開盤指數", "最高指數", "最低指數", "收盤指數")


def fetch_taiex_month(year: int, month: int, client: httpx.Client | None = None) -> dict:
    """下載某年某月的發行量加權股價指數歷史資料 JSON。"""
    if client is None:
        client = default_client()
        try:
            params = {
                "date": f"{year:04d}{month:02d}01",
                "response": "json"
            }
            response = get_with_retry(client, TAIEX_HIST_URL, params=params)
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TAIEX 回應不是 JSON 物件")
            return payload
        finally:
            client.close()
    else:
        params = {
            "date": f"{year:04d}{month:02d}01",
            "response": "json"
        }
        response = get_with_retry(client, TAIEX_HIST_URL, params=params)
        payload = response.json()
        if not isinstance(payload, dict):
            raise SourceFormatError(f"TAIEX 回應不是 JSON 物件")
        return payload


def parse_taiex_month(payload: dict, year: int, month: int) -> list[IndexRecord]:
    """把加權指數歷史 JSON 轉成 IndexRecord 清單，並過濾成只有指定年月。"""
    fields, data = extract_table(payload, TAIEX_FIELDS)

    # 取得各欄索引
    i_date = fields.index("日期")
    i_open = fields.index("開盤指數")
    i_high = fields.index("最高指數")
    i_low = fields.index("最低指數")
    i_close = fields.index("收盤指數")

    records: list[IndexRecord] = []

    for row in data:
        # 日期欄是民國格式
        date_str = str(row[i_date]).strip()
        try:
            trade_date = parse_tw_date(date_str)
        except ValueError:
            logger.warning(f"無法解析加權指數日期：{date_str}")
            continue

        # 過濾成指定年月
        if trade_date.year != year or trade_date.month != month:
            continue

        open_idx = parse_decimal(row[i_open])
        high_idx = parse_decimal(row[i_high])
        low_idx = parse_decimal(row[i_low])
        close_idx = parse_decimal(row[i_close])

        record = IndexRecord(
            index_id=TAIEX_INDEX_ID,
            trade_date=trade_date,
            open=open_idx,
            high=high_idx,
            low=low_idx,
            close=close_idx,
            volume=None
        )
        records.append(record)

    if not records:
        raise SourceFormatError(f"加權指數資料不含 {year}-{month:02d}")

    # 按 trade_date 升冪排序
    records.sort(key=lambda r: r.trade_date)
    return records
