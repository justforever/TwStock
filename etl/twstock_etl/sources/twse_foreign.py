"""外資持股 parser（上市 MI_QFIIS）。"""

import logging
import re
from datetime import date
from collections.abc import Sequence
from decimal import Decimal, ROUND_HALF_UP

import httpx

from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import ForeignHoldingRecord
from twstock_etl.numbers import clean_cell, parse_int, parse_decimal
from twstock_etl.sources.report import (
    extract_table,
    find_field,
    find_field_all,
    find_field_all_optional,
)

logger = logging.getLogger(__name__)

TWSE_QFIIS_URL = "https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS"
TWSE_QFIIS_REQUIRED_FIELDS = ("證券代號", "發行股數", "全體外資及陸資持股股數")


def fetch_twse_foreign_holding(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上市外資持股 JSON。"""
    if client is None:
        client = default_client()
        try:
            params = {
                "date": trade_date.strftime("%Y%m%d"),
                "selectType": "ALLBUT0999",
                "response": "json"
            }
            response = get_with_retry(client, TWSE_QFIIS_URL, params=params)
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TWSE 回應不是 JSON 物件：{type(payload)}")
            return payload
        finally:
            client.close()
    else:
        params = {
            "date": trade_date.strftime("%Y%m%d"),
            "selectType": "ALLBUT0999",
            "response": "json"
        }
        response = get_with_retry(client, TWSE_QFIIS_URL, params=params)
        payload = response.json()
        if not isinstance(payload, dict):
            raise SourceFormatError(f"TWSE 回應不是 JSON 物件：{type(payload)}")
        return payload


def parse_twse_foreign_holding(payload: dict, trade_date: date) -> list[ForeignHoldingRecord]:
    """把外資持股 JSON 轉成 ForeignHoldingRecord 清單（source="TWSE"）。"""
    fields, data = extract_table(payload, TWSE_QFIIS_REQUIRED_FIELDS)

    # 欄位索引查找
    i_code = find_field(fields, "證券代號", "股票代號", "代號")
    i_issued = find_field_all_optional(fields, "發行股數")
    i_holding = find_field_all(fields, "持股股數")
    i_available = find_field_all_optional(fields, "尚可投資股數")
    i_holding_ratio = find_field_all_optional(fields, "持股比率")
    i_available_ratio = find_field_all_optional(fields, "尚可投資比率")
    i_limit_ratio = find_field_all_optional(fields, "上限比率")

    records: list[ForeignHoldingRecord] = []

    for row in data:
        if len(row) < len(fields):
            logger.debug("欄位數不足，略過此列")
            continue

        stock_id = clean_cell(row[i_code])
        if not stock_id or not re.match(r"^[0-9A-Z]{4,6}$", stock_id):
            logger.debug("跳過無效代號：%r", stock_id)
            continue

        def _parse_ratio(index: int | None) -> Decimal | None:
            """解析並量化比率到 0.0001。"""
            if index is None:
                return None
            d = parse_decimal(row[index])
            if d is None:
                return None
            return d.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        record = ForeignHoldingRecord(
            stock_id=stock_id,
            trade_date=trade_date,
            issued_shares=parse_int(row[i_issued]) if i_issued is not None else None,
            holding_shares=parse_int(row[i_holding]) or 0,
            available_shares=parse_int(row[i_available]) if i_available is not None else None,
            holding_ratio=_parse_ratio(i_holding_ratio),
            available_ratio=_parse_ratio(i_available_ratio),
            limit_ratio=_parse_ratio(i_limit_ratio),
            source="TWSE",
        )
        records.append(record)

    if not records:
        raise SourceFormatError(f"{trade_date} TWSE 外資持股解析結果為空")

    return records
