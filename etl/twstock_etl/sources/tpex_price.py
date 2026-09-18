"""上櫃日成交 parser。"""

import logging
import re
from datetime import date
from decimal import Decimal

import httpx

from twstock_etl.dates import parse_tw_date
from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import PriceRecord
from twstock_etl.numbers import clean_cell, parse_decimal, parse_int
from twstock_etl.sources.report import extract_table, find_field, is_no_trade

logger = logging.getLogger(__name__)

TPEX_DAILY_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
TPEX_DAILY_URL_LEGACY = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php"
TPEX_PRICE_FIELDS = ("代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低",
                     "成交股數", "成交金額", "成交筆數")
LEGACY_COLUMNS = ("代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低",
                  "成交股數", "成交金額", "成交筆數", "最後買價", "最後買量",
                  "最後賣價", "最後賣量", "發行股數", "次日漲停價", "次日跌停價")


def fetch_tpex_daily(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上櫃每日收盤行情 JSON；新版端點失敗時自動退回舊版端點。"""
    should_close = False
    if client is None:
        client = default_client()
        should_close = True

    try:
        # 先試新版端點
        params = {
            "date": trade_date.strftime("%Y/%m/%d"),
            "type": "EW",
            "response": "json"
        }
        try:
            response = client.get(TPEX_DAILY_URL, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TPEx 回應不是 JSON 物件")
            # 試著解析確認表格可用
            try:
                extract_table(payload, TPEX_PRICE_FIELDS)
                return payload  # 成功
            except SourceFormatError:
                logger.warning(f"新版 TPEx 端點表格不符，改用舊版")
                raise  # 觸發舊版備援
        except (httpx.HTTPError, ValueError, SourceFormatError) as e:
            logger.warning(f"新版 TPEx 端點失敗（{type(e).__name__}），改用舊版")
            # 試舊版端點
            params = {
                "l": "zh-tw",
                "d": f"{trade_date.year - 1911}/{trade_date:%m/%d}",
                "o": "json"
            }
            response = get_with_retry(client, TPEX_DAILY_URL_LEGACY, params=params)
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceFormatError(f"TPEx 舊版回應不是 JSON 物件")
            return payload
    finally:
        if should_close:
            client.close()


def parse_tpex_daily(payload: dict, trade_date: date) -> list[PriceRecord]:
    """把上櫃每日收盤行情 JSON 轉成 PriceRecord 清單（source="TPEx"）。"""
    # 先判斷形狀
    if "aaData" in payload and "fields" not in payload:
        # 舊式：aaData 且沒有 fields
        fields = list(LEGACY_COLUMNS)
        data = payload.get("aaData") or []
        if not data:
            raise SourceFormatError("上櫃舊版資料表為空")

        # 比對 reportDate 與傳入日期
        if "reportDate" in payload:
            report_date_str = payload.get("reportDate")
            try:
                report_date = parse_tw_date(report_date_str)
                if report_date != trade_date:
                    raise SourceFormatError(f"上櫃舊版 reportDate {report_date_str} 與傳入日期 {trade_date} 不符")
            except ValueError:
                raise SourceFormatError(f"無法解析 reportDate：{report_date_str}")
    else:
        # 新式：用 extract_table
        fields, data = extract_table(payload, TPEX_PRICE_FIELDS)

        # 比對 date 與傳入日期
        if "date" in payload:
            date_str = payload.get("date")
            try:
                report_date = parse_tw_date(date_str)
                if report_date != trade_date:
                    raise SourceFormatError(f"上櫃新版 date {date_str} 與傳入日期 {trade_date} 不符")
            except ValueError:
                raise SourceFormatError(f"無法解析 date：{date_str}")

    # 取得各欄索引
    i_code = find_field(fields, "代號")
    i_close = find_field(fields, "收盤")
    i_change = find_field(fields, "漲跌")
    i_open = find_field(fields, "開盤")
    i_high = find_field(fields, "最高")
    i_low = find_field(fields, "最低")
    i_volume = find_field(fields, "成交股數")
    i_turnover = find_field(fields, "成交金額")
    i_transactions = find_field(fields, "成交筆數")

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

        # 上櫃漲跌欄本身就含正負號
        change = parse_decimal(row[i_change])

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
            source="TPEx"
        )
        records.append(record)

    if not records:
        raise SourceFormatError(f"{trade_date} 上櫃日成交解析結果為空")

    return records
