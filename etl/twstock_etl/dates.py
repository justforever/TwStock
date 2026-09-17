"""日期解析工具。"""

import re
from datetime import date, datetime


def parse_tw_date(value: str) -> date:
    """解析台灣官方資料常見日期格式（民國或西元）。

    接受的格式：
    - 西元 YYYY-MM-DD 或 YYYY/MM/DD
    - 西元 8 位數字 YYYYMMDD
    - 民國 7 位數字 RRRMMDD（前 3 位民國年 +1911）
    - 民國 6 位數字 RRMMDD（前 2 位民國年 +1911）
    - 民國 RRR/MM/DD 或 RR/M/D 格式

    Args:
        value: 日期字串

    Returns:
        解析後的 date 物件

    Raises:
        ValueError: 無法解析或日期無效
    """
    value = value.strip()
    if not value:
        raise ValueError(f"無法解析日期：{value!r}")

    # 嘗試西元 YYYY-MM-DD 或 YYYY/MM/DD 格式
    match = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})$", value)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return date(y, m, d)
        except ValueError:
            raise ValueError(f"無法解析日期：{value!r}")

    # 嘗試西元 8 位數字 YYYYMMDD
    if re.match(r"^\d{8}$", value):
        y, m, d = int(value[:4]), int(value[4:6]), int(value[6:8])
        try:
            return date(y, m, d)
        except ValueError:
            raise ValueError(f"無法解析日期：{value!r}")

    # 嘗試民國 7 位數字 RRRMMDD
    if re.match(r"^\d{7}$", value):
        r, m, d = int(value[:3]), int(value[3:5]), int(value[5:7])
        y = r + 1911
        try:
            return date(y, m, d)
        except ValueError:
            raise ValueError(f"無法解析日期：{value!r}")

    # 嘗試民國 6 位數字 RRMMDD
    if re.match(r"^\d{6}$", value):
        r, m, d = int(value[:2]), int(value[2:4]), int(value[4:6])
        y = r + 1911
        try:
            return date(y, m, d)
        except ValueError:
            raise ValueError(f"無法解析日期：{value!r}")

    # 嘗試民國 RRR/MM/DD 或 RR/M/D 格式
    match = re.match(r"^(\d{2,3})/(\d{1,2})/(\d{1,2})$", value)
    if match:
        r, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        y = r + 1911
        try:
            return date(y, m, d)
        except ValueError:
            raise ValueError(f"無法解析日期：{value!r}")

    raise ValueError(f"無法解析日期：{value!r}")
