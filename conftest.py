"""根目錄共用 pytest fixture。"""
import os
from typing import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from twstock_db.testing import reset_database

TEST_DB_ENV = "TWSTOCK_TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def database_url() -> str:
    """讀取測試資料庫 URL，未設定時跳過 DB 測試。"""
    url = os.environ.get(TEST_DB_ENV)
    if not url:
        pytest.skip(f"未設定 {TEST_DB_ENV}，略過 DB 測試")
    return url


@pytest.fixture(scope="session")
def db_engine(database_url: str) -> Iterator[Engine]:
    """建立 SQLAlchemy Engine 並重置資料庫。"""
    reset_database(database_url)
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture()
def clean_db(db_engine: Engine) -> Engine:
    """在每個測試前清空所有表（TRUNCATE）。"""
    from twstock_db.tables import metadata

    with db_engine.begin() as conn:
        table_names = [table.name for table in metadata.sorted_tables]
        if table_names:
            conn.execute(text(f"TRUNCATE {', '.join(table_names)}"))
    return db_engine
