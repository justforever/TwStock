"""除權除息計算結果表 parser。"""

import logging
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import httpx

from twstock_etl.dates import parse_tw_date
from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import AdjFactorRecord
from twstock_etl.numbers import parse_decimal
from twstock_etl.sources.report import extract_table, find_field

logger = logging.getLogger(__name__)

EXRIGHT_URL = "https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
EXRIGHT_FIELDS = ("資料日期", "股票代號", "除權息前收盤價", "除權息參考價")


def fetch_exright(start: date, end: date, client: httpx.Client | None = None) -> dict:
    """下載指定區間的除權除息計算結果表 JSON。"""
    if client is None:
        client = default_client()
        try:
            params = {
                "startDate": start.strftime("%Y%m%d"),
                "endDate": end.strftime("%Y%m%d"),
                "response": "json"
            }
            response = get_with_retry(client, EXRIGHT_URL, params=params)
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"除權息回應不是 JSON 物件")
            return payload
        finally:
            client.close()
    else:
        params = {
            "startDate": start.strftime("%Y%m%d"),
            "endDate": end.strftime("%Y%m%d"),
            "response": "json"
        }
        response = get_with_retry(client, EXRIGHT_URL, params=params)
        payload = response.json()
        if not isinstance(payload, dict):
            raise SourceFormatError(f"除權息回應不是 JSON 物件")
        return payload


def parse_exright(payload: dict) -> list[AdjFactorRecord]:
    """把除權除息計算結果表 JSON 轉成 AdjFactorRecord 清單。"""
    fields, data = extract_table(payload, EXRIGHT_FIELDS)

    # 取得各欄索引
    i_date = fields.index("資料日期")
    i_code = fields.index("股票代號")
    i_prev_close = fields.index("除權息前收盤價")
    i_ref_price = fields.index("除權息參考價")

    # kind 欄可能不存在
    i_kind = None
    try:
        i_kind = find_field(fields, "除權息")
    except SourceFormatError:
        pass  # 沒有 kind 欄

    records: list[AdjFactorRecord] = []

    for row in data:
        # 解析日期
        date_str = str(row[i_date]).strip()
        try:
            ex_date = parse_tw_date(date_str)
        except ValueError:
            logger.warning(f"無法解析除權息日期：{date_str}")
            continue

        # 解析代號
        stock_id = str(row[i_code]).strip()
        if not stock_id or not re.match(r"^[0-9A-Z]{4,6}$", stock_id):
            logger.debug(f"跳過無效代號：{stock_id!r}")
            continue

        # 解析價格
        prev_close = parse_decimal(row[i_prev_close])
        reference_price = parse_decimal(row[i_ref_price])

        # 檢查價格有效性
        if prev_close is None or prev_close <= 0 or reference_price is None or reference_price <= 0:
            logger.warning(f"除權息 {stock_id} {ex_date} 的價格無效或為零：prev_close={prev_close}, ref_price={reference_price}")
            continue

        # 計算因子
        factor = (reference_price / prev_close).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

        # 取得 kind
        kind = None
        if i_kind is not None:
            kind = str(row[i_kind]).strip()
            if not kind:
                kind = None

        record = AdjFactorRecord(
            stock_id=stock_id,
            ex_date=ex_date,
            factor=factor,
            prev_close=prev_close,
            reference_price=reference_price,
            kind=kind,
            source="TWSE"
        )
        records.append(record)

    # 按 (ex_date, stock_id) 升冪排序
    records.sort(key=lambda r: (r.ex_date, r.stock_id))
    return records
