"""借券賣出餘額 parser（上市 TWT93U）。單位是股，不做張→股換算。"""

import logging
import re
from datetime import date
from collections.abc import Sequence

import httpx

from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import SblRecord
from twstock_etl.numbers import clean_cell, parse_int
from twstock_etl.sources.report import (
    extract_table,
    find_field,
    find_field_all,
)

logger = logging.getLogger(__name__)

TWSE_SBL_URL = "https://www.twse.com.tw/rwd/zh/SBL/TWT93U"
TWSE_SBL_REQUIRED_FIELDS = ("股票代號", "借券賣出當日餘額")


def fetch_twse_sbl(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上市借券賣出餘額 JSON。"""
    if client is None:
        client = default_client()
        try:
            params = {
                "date": trade_date.strftime("%Y%m%d"),
                "response": "json"
            }
            response = get_with_retry(client, TWSE_SBL_URL, params=params)
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TWSE 回應不是 JSON 物件：{type(payload)}")
            return payload
        finally:
            client.close()
    else:
        params = {
            "date": trade_date.strftime("%Y%m%d"),
            "response": "json"
        }
        response = get_with_retry(client, TWSE_SBL_URL, params=params)
        payload = response.json()
        if not isinstance(payload, dict):
            raise SourceFormatError(f"TWSE 回應不是 JSON 物件：{type(payload)}")
        return payload


def parse_twse_sbl(payload: dict, trade_date: date) -> list[SblRecord]:
    """把借券賣出餘額 JSON 轉成 SblRecord 清單（source="TWSE"）。"""
    fields, data = extract_table(payload, TWSE_SBL_REQUIRED_FIELDS)

    # 欄位索引查找
    i_code = find_field(fields, "股票代號", "證券代號", "代號")
    i_sell = find_field_all(fields, "當日賣出")
    i_balance = find_field_all(fields, "當日餘額")

    records: list[SblRecord] = []

    for row in data:
        if len(row) < len(fields):
            logger.debug("欄位數不足，略過此列")
            continue

        stock_id = clean_cell(row[i_code])
        if not stock_id or not re.match(r"^[0-9A-Z]{4,6}$", stock_id):
            logger.debug("跳過無效代號：%r", stock_id)
            continue

        record = SblRecord(
            stock_id=stock_id,
            trade_date=trade_date,
            sbl_sell=parse_int(row[i_sell]) or 0,
            sbl_balance=parse_int(row[i_balance]) or 0,
            source="TWSE",
        )
        records.append(record)

    if not records:
        raise SourceFormatError(f"{trade_date} TWSE 借券賣出解析結果為空")

    return records
