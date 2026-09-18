"""上市日成交 parser。"""

import logging
import re
from datetime import date
from decimal import Decimal

import httpx

from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import PriceRecord
from twstock_etl.numbers import clean_cell, parse_decimal, parse_int, parse_sign
from twstock_etl.sources.report import extract_table, is_no_trade

logger = logging.getLogger(__name__)

TWSE_DAILY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TWSE_PRICE_FIELDS = ("證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額",
                     "開盤價", "最高價", "最低價", "收盤價", "漲跌價差")


def fetch_twse_daily(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上市每日收盤行情 JSON。"""
    if client is None:
        client = default_client()
        try:
            params = {
                "date": trade_date.strftime("%Y%m%d"),
                "type": "ALLBUT0999",
                "response": "json"
            }
            response = get_with_retry(client, TWSE_DAILY_URL, params=params)
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TWSE 回應不是 JSON 物件：{type(payload)}")
            return payload
        finally:
            client.close()
    else:
        params = {
            "date": trade_date.strftime("%Y%m%d"),
            "type": "ALLBUT0999",
            "response": "json"
        }
        response = get_with_retry(client, TWSE_DAILY_URL, params=params)
        payload = response.json()
        if not isinstance(payload, dict):
            raise SourceFormatError(f"TWSE 回應不是 JSON 物件：{type(payload)}")
        return payload


def parse_twse_daily(payload: dict, trade_date: date) -> list[PriceRecord]:
    """把上市每日收盤行情 JSON 轉成 PriceRecord 清單（source="TWSE"）。"""
    fields, data = extract_table(payload, TWSE_PRICE_FIELDS)

    # 取得各欄索引
    i_code = fields.index("證券代號")
    i_volume = fields.index("成交股數")
    i_transactions = fields.index("成交筆數")
    i_turnover = fields.index("成交金額")
    i_open = fields.index("開盤價")
    i_high = fields.index("最高價")
    i_low = fields.index("最低價")
    i_close = fields.index("收盤價")
    i_change = fields.index("漲跌價差")

    # 漲跌符號欄可能不存在或名稱不同
    i_sign = None
    try:
        i_sign = next(
            i for i, f in enumerate(fields)
            if f in ("漲跌(+/-)", "漲跌") or f.startswith("漲跌")
        )
    except StopIteration:
        pass  # 沒有符號欄

    records: list[PriceRecord] = []

    for row in data:
        stock_id = clean_cell(row[i_code])
        if not stock_id or not re.match(r"^[0-9A-Z]{4,6}$", stock_id):
            logger.debug(f"跳過無效代號：{stock_id!r}")
            continue

        volume = parse_int(row[i_volume]) or 0
        transactions = parse_int(row[i_transactions]) or 0
        turnover = parse_decimal(row[i_turnover]) or Decimal(0)

        open_price = parse_decimal(row[i_open])
        high_price = parse_decimal(row[i_high])
        low_price = parse_decimal(row[i_low])
        close_price = parse_decimal(row[i_close])

        # 判斷是否無成交
        if is_no_trade(volume, close_price):
            logger.debug(f"{trade_date} {stock_id} 無成交")
            continue

        # 計算漲跌
        diff = parse_decimal(row[i_change])
        sign = parse_sign(row[i_sign]) if i_sign is not None else 0
        change = diff * sign if (diff is not None and sign != 0) else None

        record = PriceRecord(
            stock_id=stock_id,
            trade_date=trade_date,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            change=change,
            volume=volume,
            turnover=turnover,
            transactions=transactions,
            source="TWSE"
        )
        records.append(record)

    if not records:
        raise SourceFormatError(f"{trade_date} 上市日成交解析結果為空")

    return records
