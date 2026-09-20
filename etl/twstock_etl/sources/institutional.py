"""三大法人買賣超 parser（上市 T86、上櫃 dailyTrade，含舊版備援）。"""

import logging
import re
from datetime import date
from collections.abc import Sequence

import httpx

from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import InstitutionalRecord
from twstock_etl.numbers import clean_cell, parse_int
from twstock_etl.sources.report import (
    extract_table,
    find_field,
    find_field_all,
    find_field_all_optional,
)

logger = logging.getLogger(__name__)

TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
TPEX_INST_URL = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
TPEX_INST_URL_LEGACY = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"

# 舊版備援端點只回 aaData、沒有 fields，欄位靠固定順序（順序來源：官方報表欄位標題列）
TPEX_LEGACY_INST_FIELDS = (
    "代號", "名稱",
    "外資及陸資(不含外資自營商)買進股數", "外資及陸資(不含外資自營商)賣出股數",
    "外資及陸資(不含外資自營商)買賣超股數",
    "外資自營商買進股數", "外資自營商賣出股數", "外資自營商買賣超股數",
    "外資及陸資買進股數", "外資及陸資賣出股數", "外資及陸資買賣超股數",
    "投信買進股數", "投信賣出股數", "投信買賣超股數",
    "自營商(自行買賣)買進股數", "自營商(自行買賣)賣出股數", "自營商(自行買賣)買賣超股數",
    "自營商(避險)買進股數", "自營商(避險)賣出股數", "自營商(避險)買賣超股數",
    "自營商買進股數", "自營商賣出股數", "自營商買賣超股數",
    "三大法人買賣超股數",
)

# extract_table 用來認表的必要欄位（上市／上櫃共用，用 find_field 的前綴比對找得到即可）
INSTITUTIONAL_REQUIRED_FIELDS = ("投信買進股數", "投信賣出股數", "三大法人買賣超股數")


def fetch_twse_institutional(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上市三大法人買賣超 JSON。"""
    if client is None:
        client = default_client()
        try:
            params = {
                "date": trade_date.strftime("%Y%m%d"),
                "selectType": "ALL",
                "response": "json"
            }
            response = get_with_retry(client, TWSE_T86_URL, params=params)
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
        response = get_with_retry(client, TWSE_T86_URL, params=params)
        payload = response.json()
        if not isinstance(payload, dict):
            raise SourceFormatError(f"TWSE 回應不是 JSON 物件：{type(payload)}")
        return payload


def fetch_tpex_institutional(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上櫃三大法人買賣超 JSON；新版端點失敗時自動退回舊版端點。"""
    should_close = False
    if client is None:
        client = default_client()
        should_close = True

    try:
        # 先試新版端點
        params = {
            "type": "Daily",
            "sect": "EW",
            "date": trade_date.strftime("%Y/%m/%d"),
            "response": "json"
        }
        try:
            response = client.get(TPEX_INST_URL, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TPEx 回應不是 JSON 物件")
            # 試著解析確認表格可用
            try:
                extract_table(payload, INSTITUTIONAL_REQUIRED_FIELDS)
                return payload  # 成功
            except SourceFormatError:
                logger.warning(f"新版 TPEx 法人端點表格不符，改用舊版")
                raise  # 觸發舊版備援
        except (httpx.HTTPError, ValueError, SourceFormatError) as e:
            logger.warning(f"新版 TPEx 法人端點失敗（{type(e).__name__}），改用舊版")
            # 試舊版端點
            params = {
                "l": "zh-tw",
                "se": "EW",
                "t": "D",
                "d": f"{trade_date.year - 1911}/{trade_date:%m/%d}",
                "o": "json"
            }
            response = get_with_retry(client, TPEX_INST_URL_LEGACY, params=params)
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TPEx 舊版回應不是 JSON 物件")
            return payload
    finally:
        if should_close:
            client.close()


def parse_twse_institutional(payload: dict, trade_date: date) -> list[InstitutionalRecord]:
    """把上市三大法人 JSON 轉成 InstitutionalRecord 清單（source="TWSE"）。"""
    fields, data = extract_table(payload, INSTITUTIONAL_REQUIRED_FIELDS)
    return _parse_institutional_table(fields, data, trade_date, "TWSE")


def parse_tpex_institutional(payload: dict, trade_date: date) -> list[InstitutionalRecord]:
    """把上櫃三大法人 JSON 轉成 InstitutionalRecord 清單（source="TPEx"）。"""
    # 先判形狀
    if "aaData" in payload and "fields" not in payload:
        # 舊式：aaData 且沒有 fields
        fields = list(TPEX_LEGACY_INST_FIELDS)
        data = payload.get("aaData") or []
        if not data:
            raise SourceFormatError("上櫃法人舊版資料表為空")
    else:
        fields, data = extract_table(payload, INSTITUTIONAL_REQUIRED_FIELDS)

    return _parse_institutional_table(fields, data, trade_date, "TPEx")


def _parse_institutional_table(
    fields: Sequence[str], data: Sequence[Sequence[object]], trade_date: date, source: str
) -> list[InstitutionalRecord]:
    """上市／上櫃共用的法人表格解析。"""
    # 取得各欄索引
    i_code = find_field(fields, "證券代號", "代號", "股票代號")

    # 外資欄位查找：先試主要查法，失敗時用備援
    try:
        i_f_buy = find_field_all(fields, "買進", "不含外資自營商")
    except SourceFormatError:
        i_f_buy = find_field_all(fields, "外資", "買進", exclude=("自營商",))
    
    try:
        i_f_sell = find_field_all(fields, "賣出", "不含外資自營商")
    except SourceFormatError:
        i_f_sell = find_field_all(fields, "外資", "賣出", exclude=("自營商",))

    # 外資自營商欄位（可缺）
    i_fd_buy = find_field_all_optional(fields, "外資自營商", "買進")
    i_fd_sell = find_field_all_optional(fields, "外資自營商", "賣出")

    # 投信欄位（必要）
    i_t_buy = find_field_all(fields, "投信", "買進")
    i_t_sell = find_field_all(fields, "投信", "賣出")

    # 自營商欄位：先試主要查法，失敗時用備援
    try:
        i_ds_buy = find_field_all(fields, "自營商", "自行買賣", "買進")
    except SourceFormatError:
        i_ds_buy = find_field_all(fields, "自營商", "買進", exclude=("外資", "避險"))

    try:
        i_ds_sell = find_field_all(fields, "自營商", "自行買賣", "賣出")
    except SourceFormatError:
        i_ds_sell = find_field_all(fields, "自營商", "賣出", exclude=("外資", "避險"))

    # 自營商避險欄位（可缺）
    i_dh_buy = find_field_all_optional(fields, "自營商", "避險", "買進")
    i_dh_sell = find_field_all_optional(fields, "自營商", "避險", "賣出")

    # 三大法人買賣超（可缺）
    # 三大法人買賣超（可缺）
    i_total = find_field_all_optional(fields, "三大法人", "買賣超")

    records: list[InstitutionalRecord] = []

    def cell(index: int | None) -> int:
        """輔助函式：若 index 為 None 回 0，否則取值並解析"""
        return 0 if index is None else (parse_int(row[index]) or 0)

    for row in data:
        stock_id = clean_cell(row[i_code])
        if not stock_id or not re.match(r"^[0-9A-Z]{4,6}$", stock_id):
            logger.debug("跳過無效代號：%r", stock_id)
            continue

        foreign_buy = cell(i_f_buy) + cell(i_fd_buy)
        foreign_sell = cell(i_f_sell) + cell(i_fd_sell)
        trust_buy = cell(i_t_buy)
        trust_sell = cell(i_t_sell)
        dealer_buy = cell(i_ds_buy) + cell(i_dh_buy)
        dealer_sell = cell(i_ds_sell) + cell(i_dh_sell)

        foreign_net = foreign_buy - foreign_sell
        trust_net = trust_buy - trust_sell
        dealer_net = dealer_buy - dealer_sell

        total_net = (
            parse_int(row[i_total]) if i_total is not None else None
        )
        if total_net is None:
            total_net = foreign_net + trust_net + dealer_net

        records.append(
            InstitutionalRecord(
                stock_id=stock_id,
                trade_date=trade_date,
                foreign_buy=foreign_buy,
                foreign_sell=foreign_sell,
                foreign_net=foreign_net,
                trust_buy=trust_buy,
                trust_sell=trust_sell,
                trust_net=trust_net,
                dealer_buy=dealer_buy,
                dealer_sell=dealer_sell,
                dealer_net=dealer_net,
                total_net=total_net,
                source=source,
            )
        )

    if not records:
        raise SourceFormatError(f"{trade_date} {source} 三大法人解析結果為空")

    return records
