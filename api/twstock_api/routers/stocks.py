from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from twstock_api.deps import get_db_engine
from twstock_api.repository import search_stocks
from twstock_api.schemas import StockSearchResponse

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("", response_model=StockSearchResponse)
def search(
    q: str = Query(min_length=1, max_length=50),
    limit: int = Query(default=20, ge=1, le=100),
    engine: Engine = Depends(get_db_engine),
) -> StockSearchResponse:
    """搜尋個股."""
    stripped_q = q.strip()
    if not stripped_q:
        raise HTTPException(status_code=422, detail="q 不可為空白")

    with engine.connect() as conn:
        items = search_stocks(conn, stripped_q, limit)

    return StockSearchResponse(
        query=stripped_q,
        count=len(items),
        items=items,
    )
