"""共用 JSON 報表信封工具。"""

from collections.abc import Sequence
from decimal import Decimal

from twstock_etl.errors import SourceFormatError


def find_field(fields: Sequence[str], *candidates: str) -> int:
    """在 fields 中找欄位索引：先找完全相符，再找以 candidate 開頭的欄位。

    Raises:
        SourceFormatError: 都找不到
    """
    # 先找完全相符
    for candidate in candidates:
        if candidate in fields:
            return fields.index(candidate)

    # 再找以 candidate 開頭的欄位
    for candidate in candidates:
        for i, field in enumerate(fields):
            if field.startswith(candidate):
                return i

    raise SourceFormatError(f"找不到欄位：{candidates}")


def extract_table(
    payload: object, required_fields: Sequence[str]
) -> tuple[list[str], list[list[object]]]:
    """從 TWSE / TPEx 報表 JSON 取出含指定欄位的表格，回傳 (fields, data)。

    支援三種形狀：
    1. {"tables": [{"fields": [...], "data": [[...]]}, ...]}  → 取第一個欄位滿足的表
    2. {"fields": [...], "data": [[...]]}                      → 頂層單表
    3. {"fields": [...], "aaData": [[...]]}                    → 頂層單表（舊式鍵名）

    「欄位滿足」的判定：required_fields 中每一個都能用 find_field 在該表 fields 內找到。

    Raises:
        SourceFormatError: payload 不是 dict、stat 不是 OK、找不到符合的表、data 為空
    """
    if not isinstance(payload, dict):
        raise SourceFormatError("來源回應不是 JSON 物件")

    # 檢查 stat 欄位
    if "stat" in payload:
        stat = str(payload.get("stat", "")).strip().upper()
        if stat != "OK":
            raise SourceFormatError(f"來源回應 stat 非 OK：{payload.get('stat')}")

    # 嘗試形狀 1：tables 陣列
    if "tables" in payload:
        tables = payload.get("tables")
        if isinstance(tables, list):
            for table in tables:
                if not isinstance(table, dict):
                    continue
                fields = table.get("fields", [])
                # 檢查是否所有 required_fields 都能找到
                try:
                    for required in required_fields:
                        find_field(fields, required)
                except SourceFormatError:
                    continue  # 這個表欄位不符，繼續找下一個

                # 找到符合的表，檢查 data
                data = table.get("data") or table.get("aaData") or []
                if not data:
                    raise SourceFormatError("資料表為空")
                return list(fields), data

    # 嘗試形狀 2：頂層單表（fields + data）
    if "fields" in payload and "data" in payload:
        fields = payload.get("fields", [])
        data = payload.get("data") or []
        # 檢查是否所有 required_fields 都能找到
        for required in required_fields:
            find_field(fields, required)
        if not data:
            raise SourceFormatError("資料表為空")
        return list(fields), data

    # 嘗試形狀 3：頂層單表（fields + aaData）
    if "fields" in payload and "aaData" in payload:
        fields = payload.get("fields", [])
        data = payload.get("aaData") or []
        # 檢查是否所有 required_fields 都能找到
        for required in required_fields:
            find_field(fields, required)
        if not data:
            raise SourceFormatError("資料表為空")
        return list(fields), data

    raise SourceFormatError("找不到符合條件的資料表")


def is_no_trade(volume: int, close: Decimal | None) -> bool:
    """判斷是否為「當日無成交」：成交股數為 0 且收盤價為空或 0。"""
    return volume == 0 and (close is None or close == 0)


def find_field_all(
    fields: Sequence[str],
    *tokens: str,
    exclude: Sequence[str] = (),
) -> int:
    """回傳第一個「同時包含 tokens 全部關鍵字、且不含 exclude 任一關鍵字」的欄位索引。

    Args:
        fields: 欄位名稱清單
        tokens: 必須全部出現在欄位名稱裡的關鍵字
        exclude: 只要出現任一個就排除該欄位

    Raises:
        SourceFormatError: 找不到
    """
    from twstock_etl.numbers import clean_cell

    # 先找不包含括號的精確匹配（優先級較高）
    for i, field in enumerate(fields):
        if '(' in field or ')' in field:
            continue
        cleaned = clean_cell(field)
        # 檢查所有 tokens 是否都在欄位名稱內
        if not all(token in cleaned for token in tokens):
            continue
        # 檢查是否包含任一個 exclude 的關鍵字
        if any(exc in cleaned for exc in exclude):
            continue
        return i

    # 如果沒有找到，再尋找包含括號的欄位
    for i, field in enumerate(fields):
        cleaned = clean_cell(field)
        # 檢查所有 tokens 是否都在欄位名稱內
        if not all(token in cleaned for token in tokens):
            continue
        # 檢查是否包含任一個 exclude 的關鍵字
        if any(exc in cleaned for exc in exclude):
            continue
        return i

    raise SourceFormatError(f"找不到欄位：所有必要關鍵字 {tokens}，排除關鍵字 {exclude}")


def find_field_all_optional(
    fields: Sequence[str], *tokens: str, exclude: Sequence[str] = ()
) -> int | None:
    """同 find_field_all，但找不到時回 None（給「舊格式沒有這一欄」的情況用）。"""
    try:
        return find_field_all(fields, *tokens, exclude=exclude)
    except SourceFormatError:
        return None
