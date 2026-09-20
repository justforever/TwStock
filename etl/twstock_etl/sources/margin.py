"""融資融券 parser（上市 MI_MARGN、上櫃 margin/balance，含舊版備援）。"""

import logging
import re
from datetime import date
from collections.abc import Sequence

import httpx

from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import MarginRecord
from twstock_etl.numbers import clean_cell, parse_int
from twstock_etl.sources.report import (
    extract_table,
    find_field,
    find_field_all,
    find_field_all_optional,
)

logger = logging.getLogger(__name__)

TWSE_MARGIN_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
TPEX_MARGIN_URL = "https://www.tpex.org.tw/www/zh-tw/margin/balance"
TPEX_MARGIN_URL_LEGACY = "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php"

TWSE_MARGIN_REQUIRED_FIELDS = ("股票代號", "融資今日餘額", "融券今日餘額")
TPEX_MARGIN_REQUIRED_FIELDS = ("代號", "資餘額", "券餘額")

TPEX_LEGACY_MARGIN_FIELDS = (
    "代號", "名稱", "前資餘額(張)", "資買", "資賣", "現償", "資餘額", "資屬證金",
    "資使用率(%)", "資限額", "前券餘額(張)", "券賣", "券買", "券償", "券餘額",
    "券屬證金", "券使用率(%)", "券限額", "資券相抵", "備註",
)

SHARES_PER_LOT = 1000


def fetch_twse_margin(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上市融資融券 JSON。"""
    if client is None:
        client = default_client()
        try:
            params = {
                "date": trade_date.strftime("%Y%m%d"),
                "selectType": "ALL",
                "response": "json"
            }
            response = get_with_retry(client, TWSE_MARGIN_URL, params=params)
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TWSE 回應不是 JSON 物件：{type(payload)}")
            return payload
        finally:
            client.close()
    else:
        params = {
            "date": trade_date.strftime("%Y%m%d"),
            "selectType": "ALL",
            "response": "json"
        }
        response = get_with_retry(client, TWSE_MARGIN_URL, params=params)
        payload = response.json()
        if not isinstance(payload, dict):
            raise SourceFormatError(f"TWSE 回應不是 JSON 物件：{type(payload)}")
        return payload


def fetch_tpex_margin(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上櫃融資融券 JSON；新版端點失敗時自動退回舊版端點。"""
    should_close = False
    if client is None:
        client = default_client()
        should_close = True

    try:
        # 先試新版端點
        params = {
            "date": trade_date.strftime("%Y/%m/%d"),
            "response": "json"
        }
        try:
            response = client.get(TPEX_MARGIN_URL, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TPEx 回應不是 JSON 物件")
            # 試著解析確認表格可用
            try:
                extract_table(payload, TPEX_MARGIN_REQUIRED_FIELDS)
                return payload  # 成功
            except SourceFormatError:
                raise  # 表格格式錯誤，直接拋出改用舊版
        except (httpx.HTTPError, ValueError, SourceFormatError) as e:
            logger.warning("新版 TPEx 融資融券端點失敗（%s），改用舊版", e)
            # 改用舊版端點
            params = {
                "l": "zh-tw",
                "d": f"{trade_date.year - 1911}/{trade_date:%m/%d}",
                "o": "json"
            }
            response = client.get(TPEX_MARGIN_URL_LEGACY, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TPEx 舊版回應不是 JSON 物件")
            return payload
    finally:
        if should_close:
            client.close()


def parse_twse_margin(payload: dict, trade_date: date) -> list[MarginRecord]:
    """把上市融資融券 JSON 轉成 MarginRecord 清單（source="TWSE"）。"""
    fields, data = extract_table(payload, TWSE_MARGIN_REQUIRED_FIELDS)
    return _parse_margin_table(fields, data, trade_date, "TWSE")


def parse_tpex_margin(payload: dict, trade_date: date) -> list[MarginRecord]:
    """把上櫃融資融券 JSON 轉成 MarginRecord 清單（source="TPEx"）。"""
    if "aaData" in payload and "fields" not in payload:
        # 舊版格式
        fields = list(TPEX_LEGACY_MARGIN_FIELDS)
        data = payload["aaData"]
        if not data:
            raise SourceFormatError("上櫃融資融券舊版資料表為空")
    else:
        fields, data = extract_table(payload, TPEX_MARGIN_REQUIRED_FIELDS)
    return _parse_margin_table(fields, data, trade_date, "TPEx")


def _parse_margin_table(
    fields: Sequence[str], data: Sequence[Sequence[object]], trade_date: date, source: str
) -> list[MarginRecord]:
    """上市／上櫃共用的融資融券表格解析。"""
    # 欄位索引查找
    i_code = find_field(fields, "代號", "股票代號", "證券代號")

    if source == "TWSE":
        # 上市欄位查找
        i_mb = find_field_all(fields, "融資", "買進")
        i_ms = find_field_all(fields, "融資", "賣出")
        i_mr = find_field_all(fields, "現金償還")
        i_mpb = find_field_all(fields, "融資", "前日餘額")
        i_mbal = find_field_all(fields, "融資", "今日餘額")
        i_mlim = find_field_all_optional(fields, "融資", "限額")
        i_sb = find_field_all(fields, "融券", "買進")
        i_ss = find_field_all(fields, "融券", "賣出")
        i_sr = find_field_all(fields, "現券償還")
        i_spb = find_field_all(fields, "融券", "前日餘額")
        i_sbal = find_field_all(fields, "融券", "今日餘額")
        i_slim = find_field_all_optional(fields, "融券", "限額")
        i_offset = find_field_all_optional(fields, "資券互抵")
    else:
        # 上櫃欄位查找
        i_mpb = find_field_all(fields, "前資餘額")
        i_mb = find_field_all(fields, "資買")
        i_ms = find_field_all(fields, "資賣")
        i_mr = find_field_all(fields, "現償")
        i_mbal = find_field_all(fields, "資餘額", exclude=("前",))
        i_mlim = find_field_all_optional(fields, "資限額")
        i_spb = find_field_all(fields, "前券餘額")
        i_ss = find_field_all(fields, "券賣")
        i_sb = find_field_all(fields, "券買")
        i_sr = find_field_all(fields, "券償")
        i_sbal = find_field_all(fields, "券餘額", exclude=("前",))
        i_slim = find_field_all_optional(fields, "券限額")
        i_offset = find_field_all_optional(fields, "資券相抵") or find_field_all_optional(fields, "資券互抵")

    records: list[MarginRecord] = []

    for row in data:
        if len(row) < len(fields):
            logger.debug("欄位數不足，略過此列")
            continue

        stock_id = clean_cell(row[i_code])
        if not stock_id or not re.match(r"^[0-9A-Z]{4,6}$", stock_id):
            logger.debug("跳過無效代號：%r", stock_id)
            continue

        def lots(index: int | None) -> int:
            """張 → 股；欄位不存在或空值一律 0。"""
            return 0 if index is None else (parse_int(row[index]) or 0) * SHARES_PER_LOT

        def lots_optional(index: int | None) -> int | None:
            """張 → 股；欄位不存在或是 '-' / 空白時回 None（限額欄用）。"""
            if index is None:
                return None
            value = parse_int(row[index])
            return None if value is None else value * SHARES_PER_LOT

        record = MarginRecord(
            stock_id=stock_id,
            trade_date=trade_date,
            margin_buy=lots(i_mb),
            margin_sell=lots(i_ms),
            margin_redeem=lots(i_mr),
            margin_prev_balance=lots(i_mpb),
            margin_balance=lots(i_mbal),
            margin_limit=lots_optional(i_mlim),
            short_buy=lots(i_sb),
            short_sell=lots(i_ss),
            short_redeem=lots(i_sr),
            short_prev_balance=lots(i_spb),
            short_balance=lots(i_sbal),
            short_limit=lots_optional(i_slim),
            offset_amount=lots(i_offset),
            source=source,
        )
        records.append(record)

    if not records:
        raise SourceFormatError(f"{trade_date} {source} 融資融券解析結果為空")

    return records
