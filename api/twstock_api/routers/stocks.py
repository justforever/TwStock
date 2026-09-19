from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from twstock_api.deps import get_db_engine
from twstock_api.price_repository import latest_bar, get_stock
from twstock_api.repository import search_stocks
from twstock_api.schemas import StockSearchResponse, StockDetail, PriceBar

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


@router.get("/{stock_id}", response_model=StockDetail)
def get_stock_detail(
    stock_id: str,
    engine: Engine = Depends(get_db_engine),
) -> StockDetail:
    """取得個股詳細資訊。"""
    with engine.connect() as conn:
        stock = get_stock(conn, stock_id)
        if not stock:
            raise HTTPException(status_code=404, detail=f"查無此個股：{stock_id}")

        # 取得最新 K 棒
        latest = latest_bar(conn, stock_id)
        latest_bar_obj = None
        if latest:
            latest_bar_obj = PriceBar(
                time=latest["trade_date"],
                open=float(latest["open"]) if latest["open"] is not None else None,
                high=float(latest["high"]) if latest["high"] is not None else None,
                low=float(latest["low"]) if latest["low"] is not None else None,
                close=float(latest["close"]) if latest["close"] is not None else None,
                change=float(latest["change"]) if latest["change"] is not None else None,
                volume=int(latest["volume"]),
                turnover=float(latest["turnover"]),
                transactions=int(latest["transactions"]),
            )

    return StockDetail(
        stock_id=stock["stock_id"],
        name=stock["name"],
        market=stock["market"],
        industry=stock["industry"],
        listed_date=stock["listed_date"],
        is_etf=stock["is_etf"],
        is_active=stock["is_active"],
        latest=latest_bar_obj,
    )
