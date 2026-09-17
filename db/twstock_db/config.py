"""資料庫連線設定。"""
import os

DATABASE_URL_ENV = "DATABASE_URL"


def get_database_url() -> str:
    """從環境變數 DATABASE_URL 讀取 SQLAlchemy 連線字串。"""
    url = os.environ.get(DATABASE_URL_ENV)
    if not url:
        raise RuntimeError(f"環境變數 {DATABASE_URL_ENV} 未設定")
    return url
