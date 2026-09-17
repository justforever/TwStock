import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from twstock_api.deps import get_db_engine
from twstock_api.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(engine: Engine = Depends(get_db_engine)) -> JSONResponse | HealthResponse:
    """健康檢查：檢查 DB 連線."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return HealthResponse(status="ok", db="ok")
    except SQLAlchemyError:
        logger.exception("DB 連線失敗")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "db": "unreachable"},
        )
