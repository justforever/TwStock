"""集保股權分散（TDCC 開放資料）parser。"""

import csv
import io
import logging
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import httpx

from twstock_etl.dates import parse_tw_date
from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import ShareholdingRecord
from twstock_etl.numbers import clean_cell, parse_decimal, parse_int
from twstock_etl.sources.report import find_field

logger = logging.getLogger(__name__)

TDCC_URL = "https://opendata.tdcc.com.tw/getOD.ashx"
TDCC_DATASET_ID = "1-5"
TDCC_HEADER_FIELDS = ("資料日期", "證券代號", "持股分級", "人數", "股數", "占集保庫存數比例")


def fetch_tdcc_shareholding(client: httpx.Client | None = None) -> str:
    """下載集保股權分散 CSV 原文（UTF-8 字串）。"""
    if client is None:
        client = default_client()
        try:
            return get_with_retry(client, TDCC_URL, params={"id": TDCC_DATASET_ID}).text
        finally:
            client.close()
    else:
        return get_with_retry(client, TDCC_URL, params={"id": TDCC_DATASET_ID}).text


def parse_tdcc_shareholding(text: str) -> list[ShareholdingRecord]:
    """把集保股權分散 CSV 轉成 ShareholdingRecord 清單。

    Raises:
        SourceFormatError: 表頭缺欄位、或解析結果為空
    """
    # 移除 BOM
    text = text.lstrip("﻿")

    # 解析 CSV
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows) < 2:
        raise SourceFormatError("集保股權分散 CSV 沒有資料列")

    # 解析表頭
    header = [clean_cell(c) for c in rows[0]]
    i_date = find_field(header, "資料日期")
    i_code = find_field(header, "證券代號")
    i_level = find_field(header, "持股分級")
    i_holders = find_field(header, "人數")
    i_shares = find_field(header, "股數")
    i_ratio = find_field(header, "占集保庫存數比例")

    records: list[ShareholdingRecord] = []

    # 逐列解析資料
    for row in rows[1:]:
        # 檢查欄位數
        if len(row) < len(header):
            logger.debug("欄位數不足，略過此列：%r", row)
            continue

        # 解析股票代號
        stock_id = clean_cell(row[i_code])
        if not stock_id or not re.match(r"^[0-9A-Z]{4,6}$", stock_id):
            logger.debug("跳過無效代號：%r", stock_id)
            continue

        # 解析資料日期
        week_date = _parse_tdcc_date(clean_cell(row[i_date]))
        if week_date is None:
            logger.debug("無法解析日期：%r", row[i_date])
            continue

        # 解析持股分級
        level = parse_int(clean_cell(row[i_level]))
        if level is None or not (1 <= level <= 17):
            logger.warning("略過不支援的持股分級 %r", clean_cell(row[i_level]))
            continue

        # 解析人數與股數
        holders = parse_int(clean_cell(row[i_holders])) or 0
        shares = parse_int(clean_cell(row[i_shares])) or 0

        # 解析比率
        ratio = (parse_decimal(clean_cell(row[i_ratio])) or Decimal(0)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

        records.append(
            ShareholdingRecord(
                stock_id=stock_id,
                week_date=week_date,
                level=level,
                holders=holders,
                shares=shares,
                ratio=ratio,
            )
        )

    if not records:
        raise SourceFormatError("集保股權分散解析結果為空")

    return records


def _parse_tdcc_date(value: str) -> date | None:
    """解析集保資料日期；不認得回 None。

    直接包 M1 既有的 `twstock_etl.dates.parse_tw_date`（已支援 'YYYYMMDD'、
    'YYYY/MM/DD'、民國格式），只是把 ValueError 轉成 None。
    """
    try:
        return parse_tw_date(value)
    except ValueError:
        return None
