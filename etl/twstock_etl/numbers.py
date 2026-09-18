"""數值清洗工具。"""

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from twstock_etl.errors import SourceFormatError

NULL_TOKENS = frozenset({"", "-", "--", "---", "X", "x", "N/A", "n/a", "null", "None", "免評", "不適用"})
_TAG_RE = re.compile(r"<[^>]*>")


def clean_cell(value: object) -> str:
    """把報表儲存格轉成乾淨字串：去 HTML 標籤、去千分位逗號、去全形空白與前後空白、去加號。"""
    # str(value) → 移除 _TAG_RE 匹配到的標籤 → replace("　", "") → replace(",", "") → strip() → 若開頭是 + 就去掉
    text = str(value)
    text = _TAG_RE.sub("", text)  # 移除 HTML 標籤
    text = text.replace("　", "")  # 去全形空白
    text = text.replace(",", "")  # 去千分位逗號
    text = text.strip()  # 去前後空白
    if text.startswith("+"):
        text = text[1:]  # 去加號
    return text


def parse_decimal(value: object) -> Decimal | None:
    """把儲存格轉成 Decimal；空值或 NULL_TOKENS 回傳 None。

    Raises:
        SourceFormatError: 清洗後既不是空值也不是合法數字
    """
    cleaned = clean_cell(value)
    if not cleaned or cleaned in NULL_TOKENS:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise SourceFormatError(f"無法解析為數字：{value!r}")


def parse_int(value: object) -> int | None:
    """把儲存格轉成 int（先走 parse_decimal 再取整數部分）；空值回傳 None。"""
    decimal_val = parse_decimal(value)
    if decimal_val is None:
        return None
    return int(decimal_val)


def parse_sign(value: object) -> int:
    """解析 TWSE 的「漲跌(+/-)」欄位，回傳 1 / -1 / 0。

    清洗後含 '+' → 1；含 '-' → -1；其餘（含 'X'、空字串）→ 0。
    """
    # 先檢查原始值中是否有 + 或 - 符號
    text = str(value)
    if "+" in text:
        return 1
    elif "-" in text:
        return -1
    else:
        return 0
