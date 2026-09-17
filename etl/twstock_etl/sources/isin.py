"""ISIN 一覽表 parser（TWSE 上市與 TPEx 上櫃）。"""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from twstock_etl.dates import parse_tw_date
from twstock_etl.errors import SourceFormatError
from twstock_etl.http import default_client, get_with_retry
from twstock_etl.models import StockRecord

logger = logging.getLogger(__name__)

ISIN_URLS = {
    "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
    "TPEx": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",
}

STOCK_SECTIONS = frozenset({"股票", "創新板股票"})
ETF_SECTIONS = frozenset({"ETF"})
_CODE_RE = re.compile(r"^[0-9A-Z]{4,6}$")


def decode_isin_bytes(raw: bytes) -> str:
    """ISIN 網頁為 MS950 編碼：先試 cp950 嚴格解碼，失敗改用 big5hkscs。

    Args:
        raw: 原始位元組

    Returns:
        解碼後的字串

    Raises:
        UnicodeDecodeError: 兩種編碼都失敗
    """
    try:
        return raw.decode("cp950")
    except UnicodeDecodeError:
        return raw.decode("big5hkscs", errors="replace")


def fetch_isin_html(market: str, client: httpx.Client | None = None) -> str:
    """下載指定市場的 ISIN 一覽表。

    Args:
        market: "TWSE" 或 "TPEx"
        client: httpx.Client 實例；為 None 時建立新的

    Returns:
        解碼後的 HTML 字串

    Raises:
        ValueError: market 不合法
        SourceFormatError: 網路或格式錯誤
    """
    if market not in ISIN_URLS:
        raise ValueError(f"不支援的市場：{market}")

    if client is None:
        client = default_client()
        should_close = True
    else:
        should_close = False

    try:
        url = ISIN_URLS[market]
        response = get_with_retry(client, url)
        response.raise_for_status()
        return decode_isin_bytes(response.content)
    finally:
        if should_close:
            client.close()


def parse_isin_html(html: str, market: str) -> list[StockRecord]:
    """解析 ISIN 一覽表 HTML，只保留「股票」「創新板股票」「ETF」區段。

    Args:
        html: HTML 字串
        market: "TWSE" 或 "TPEx"

    Returns:
        StockRecord 清單

    Raises:
        ValueError: market 不合法
        SourceFormatError: 解析結果為空或其他格式問題
    """
    if market not in ("TWSE", "TPEx"):
        raise ValueError(f"不支援的市場：{market}")

    soup = BeautifulSoup(html, "html.parser")
    current_section: str | None = None
    seen: set[str] = set()
    records: list[StockRecord] = []

    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        cells = [td.get_text(strip=True) for td in tds]

        if len(tds) == 1:
            # 區段列
            current_section = cells[0]
            continue

        if len(tds) >= 7:
            # 資料列
            if cells[0].startswith("有價證券代號及名稱"):
                # 表頭
                continue

            if current_section not in STOCK_SECTIONS | ETF_SECTIONS:
                # 不在關注的區段
                continue

            # 拆代號與名稱
            # 先嘗試全形空白 U+3000
            code, name = None, None
            if "　" in cells[0]:
                parts = cells[0].split("　", 1)
                if len(parts) == 2:
                    code, name = parts[0].strip(), parts[1].strip()

            # 退而求其次：半形空白
            if code is None or name is None:
                parts = cells[0].split(None, 1)
                if len(parts) == 2:
                    code, name = parts[0].strip(), parts[1].strip()

            if code is None or name is None:
                logger.warning(f"無法拆分代號與名稱：{cells[0]!r}")
                continue

            # 代號驗證
            if not _CODE_RE.match(code):
                logger.warning(f"代號不符合格式：{code!r}")
                continue

            if code in seen:
                # 已出現過，保留第一筆
                continue
            seen.add(code)

            # 上市日期
            listed_date = None
            if cells[2]:  # cells[2] 是上市日
                try:
                    listed_date = parse_tw_date(cells[2])
                except ValueError:
                    logger.warning(
                        f"代號 {code} 的上市日期無法解析：{cells[2]!r}"
                    )
                    # 不跳過該列，設為 None

            # 產業別、ISIN、CFI
            industry = cells[4] or None
            isin_code = cells[1] or None
            cfi_code = cells[5] or None
            is_etf = current_section in ETF_SECTIONS

            record = StockRecord(
                stock_id=code,
                name=name,
                market=market,  # type: ignore
                industry=industry,
                listed_date=listed_date,
                is_etf=is_etf,
                isin_code=isin_code,
                cfi_code=cfi_code,
            )
            records.append(record)

    if not records:
        raise SourceFormatError(
            f"ISIN 一覽表解析結果為空（market={market}），可能是格式變動"
        )

    return records
