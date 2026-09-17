"""資料庫測試工具。"""
from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config(database_url: str) -> Config:
    """回傳指向 db/alembic.ini、並設定好 sqlalchemy.url 的 Alembic Config。"""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def reset_database(database_url: str) -> None:
    """把測試資料庫降到 base 再升到 head（清空所有表與結構）。"""
    cfg = alembic_config(database_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
