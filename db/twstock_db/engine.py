"""SQLAlchemy Engine 工廠。"""
from functools import lru_cache

from sqlalchemy import Engine, create_engine

from .config import get_database_url


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    """建立（並快取）SQLAlchemy Engine；url 為 None 時讀 DATABASE_URL。"""
    connection_url = url or get_database_url()
    return create_engine(connection_url, pool_pre_ping=True)
