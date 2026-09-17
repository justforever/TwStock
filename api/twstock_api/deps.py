from sqlalchemy.engine import Engine

from twstock_db.engine import get_engine


def get_db_engine() -> Engine:
    """FastAPI dependency：回傳 twstock_db.engine.get_engine()."""
    return get_engine()
