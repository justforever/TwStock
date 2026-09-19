"""個股價格 API 路由."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from twstock_api.adjust import apply_adjustment
from twstock_api.deps import get_db_engine
from twstock_api.price_repository import (
    DEFAULT_LIMIT,
    DEFAULT_WINDOW_DAYS,
    MAX_LIMIT,
    fetch_adj_factors,
    fetch_prices,
    get_stock,
    latest_price_date,
)
from twstock_api.schemas import PriceBar, PriceResponse

router = APIRouter(prefix="/api/stocks", tags=["prices"])


@router.get("/{stock_id}/prices", response_model=PriceResponse)
def get_prices(
    stock_id: str,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    adj: bool = Query(default=False),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    engine: Engine = Depends(get_db_engine),
) -> PriceResponse:
    """查詢個股日 K，支援還原價。"""
    with engine.connect() as conn:
        stock = get_stock(conn, stock_id)
        if not stock:
            raise HTTPException(status_code=404, detail=f"查無此個股：{stock_id}")

        # 決定 to 日期
        if to is None:
            latest_date = latest_price_date(conn, stock_id)
            if latest_date is None:
                to = datetime.now(ZoneInfo("Asia/Taipei")).date()
            else:
                to = latest_date

        # 決定 from 日期
        if from_ is None:
            from_ = to - timedelta(days=DEFAULT_WINDOW_DAYS)

        # 驗證日期範圍
        if from_ > to:
            raise HTTPException(status_code=422, detail="from 不可晚於 to")

        # 取得日 K
        bars = fetch_prices(conn, stock_id, from_, to, limit)

        # 套用還原係數
        if adj and bars:
            factors = fetch_adj_factors(conn, stock_id, to)
            bars = apply_adjustment(bars, factors)

        # 轉換為 PriceBar
        items = []
        for bar in bars:
            items.append(
                PriceBar(
                    time=bar["trade_date"],
                    open=float(bar["open"]) if bar["open"] is not None else None,
                    high=float(bar["high"]) if bar["high"] is not None else None,
                    low=float(bar["low"]) if bar["low"] is not None else None,
                    close=float(bar["close"]) if bar["close"] is not None else None,
                    change=float(bar["change"]) if bar["change"] is not None else None,
                    volume=int(bar["volume"]),
                    turnover=float(bar["turnover"]),
                    transactions=int(bar["transactions"]),
                )
            )

        return PriceResponse(
            stock_id=stock_id,
            name=stock["name"],
            market=stock["market"],
            adjusted=adj,
            from_=from_,
            to=to,
            count=len(items),
            items=items,
        )
