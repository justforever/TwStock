"""ETL 異常類型定義。"""


class SourceFormatError(Exception):
    """來源資料格式不符預期（欄位缺漏、解析結果為空、筆數異常）。"""
