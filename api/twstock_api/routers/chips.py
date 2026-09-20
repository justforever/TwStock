"""籌碼資料 API 路由."""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from twstock_api.chip_repository import (
    DEFAULT_LIMIT,
    DEFAULT_WINDOW_DAYS,
    SHAREHOLDING_DEFAULT_LIMIT,
    SHAREHOLDING_MAX_LIMIT,
    MAX_LIMIT,
    fetch_institutional,
    fetch_margin,
    fetch_foreign_holding,
    fetch_shareholding,
    latest_chip_date,
)
from twstock_api.deps import get_db_engine
from twstock_api.price_repository import get_stock
from twstock_api.schemas import (
    InstitutionalBar,
    InstitutionalResponse,
    MarginBar,
    MarginResponse,
    ForeignHoldingBar,
    ForeignHoldingResponse,
    ShareholdingLevel,
    ShareholdingWeek,
    ShareholdingResponse,
)

router = APIRouter(prefix="/api/stocks", tags=["chips"])


def _resolve(
    conn,
    stock_id: str,
    from_: date | None,
    to: date | None,
    kind: str,
) -> tuple[dict, date, date]:
    """共用的「查個股 + 決定日期區間」流程。

    Raises:
        HTTPException: 404 個股不存在、422 from > to
    """
    stock = get_stock(conn, stock_id)
    if not stock:
        raise HTTPException(status_code=404, detail=f"查無此個股：{stock_id}")

    if to is None:
        latest = latest_chip_date(conn, kind, stock_id)
        to = latest if latest is not None else datetime.now(ZoneInfo("Asia/Taipei")).date()

    if from_ is None:
        from_ = to - timedelta(days=DEFAULT_WINDOW_DAYS)

    if from_ > to:
        raise HTTPException(status_code=422, detail="from 不可晚於 to")

    return stock, from_, to


@router.get("/{stock_id}/institutional", response_model=InstitutionalResponse)
def get_institutional(
    stock_id: str,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    engine: Engine = Depends(get_db_engine),
) -> InstitutionalResponse:
    """查詢個股三大法人買賣超。"""
    with engine.connect() as conn:
        stock, from_, to = _resolve(conn, stock_id, from_, to, "institutional")

        bars = fetch_institutional(conn, stock_id, from_, to, limit)

        items = []
        for bar in bars:
            items.append(
                InstitutionalBar(
                    time=bar["trade_date"],
                    foreign_buy=int(bar["foreign_buy"]),
                    foreign_sell=int(bar["foreign_sell"]),
                    foreign_net=int(bar["foreign_net"]),
                    trust_buy=int(bar["trust_buy"]),
                    trust_sell=int(bar["trust_sell"]),
                    trust_net=int(bar["trust_net"]),
                    dealer_buy=int(bar["dealer_buy"]),
                    dealer_sell=int(bar["dealer_sell"]),
                    dealer_net=int(bar["dealer_net"]),
                    total_net=int(bar["total_net"]),
                )
            )

        return InstitutionalResponse(
            stock_id=stock_id,
            name=stock["name"],
            market=stock["market"],
            from_=from_,
            to=to,
            count=len(items),
            items=items,
        )


@router.get("/{stock_id}/margin", response_model=MarginResponse)
def get_margin(
    stock_id: str,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    engine: Engine = Depends(get_db_engine),
) -> MarginResponse:
    """查詢個股融資融券與借券。"""
    with engine.connect() as conn:
        stock, from_, to = _resolve(conn, stock_id, from_, to, "margin")

        bars = fetch_margin(conn, stock_id, from_, to, limit)

        items = []
        for bar in bars:
            # 計算 margin_ratio
            margin_ratio = None
            if bar["margin_balance"] and bar["margin_balance"] != 0:
                ratio_dec = Decimal(bar["short_balance"]) / Decimal(bar["margin_balance"]) * Decimal("100")
                margin_ratio = float(ratio_dec.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))

            items.append(
                MarginBar(
                    time=bar["trade_date"],
                    margin_buy=int(bar["margin_buy"]),
                    margin_sell=int(bar["margin_sell"]),
                    margin_redeem=int(bar["margin_redeem"]),
                    margin_prev_balance=int(bar["margin_prev_balance"]),
                    margin_balance=int(bar["margin_balance"]),
                    margin_limit=int(bar["margin_limit"]) if bar["margin_limit"] is not None else None,
                    short_buy=int(bar["short_buy"]),
                    short_sell=int(bar["short_sell"]),
                    short_redeem=int(bar["short_redeem"]),
                    short_prev_balance=int(bar["short_prev_balance"]),
                    short_balance=int(bar["short_balance"]),
                    short_limit=int(bar["short_limit"]) if bar["short_limit"] is not None else None,
                    offset_amount=int(bar["offset_amount"]),
                    sbl_sell=int(bar["sbl_sell"]) if bar["sbl_sell"] is not None else None,
                    sbl_balance=int(bar["sbl_balance"]) if bar["sbl_balance"] is not None else None,
                    margin_ratio=margin_ratio,
                )
            )

        return MarginResponse(
            stock_id=stock_id,
            name=stock["name"],
            market=stock["market"],
            from_=from_,
            to=to,
            count=len(items),
            items=items,
        )


@router.get("/{stock_id}/foreign-holding", response_model=ForeignHoldingResponse)
def get_foreign_holding(
    stock_id: str,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    engine: Engine = Depends(get_db_engine),
) -> ForeignHoldingResponse:
    """查詢個股外資持股。"""
    with engine.connect() as conn:
        stock, from_, to = _resolve(conn, stock_id, from_, to, "foreign")

        bars = fetch_foreign_holding(conn, stock_id, from_, to, limit)

        items = []
        for bar in bars:
            items.append(
                ForeignHoldingBar(
                    time=bar["trade_date"],
                    issued_shares=int(bar["issued_shares"]) if bar["issued_shares"] is not None else None,
                    holding_shares=int(bar["holding_shares"]),
                    available_shares=int(bar["available_shares"]) if bar["available_shares"] is not None else None,
                    holding_ratio=float(bar["holding_ratio"]) if bar["holding_ratio"] is not None else None,
                    available_ratio=float(bar["available_ratio"]) if bar["available_ratio"] is not None else None,
                    limit_ratio=float(bar["limit_ratio"]) if bar["limit_ratio"] is not None else None,
                )
            )

        return ForeignHoldingResponse(
            stock_id=stock_id,
            name=stock["name"],
            market=stock["market"],
            from_=from_,
            to=to,
            count=len(items),
            items=items,
        )


@router.get("/{stock_id}/shareholding", response_model=ShareholdingResponse)
def get_shareholding(
    stock_id: str,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    limit: int = Query(default=SHAREHOLDING_DEFAULT_LIMIT, ge=1, le=SHAREHOLDING_MAX_LIMIT),
    engine: Engine = Depends(get_db_engine),
) -> ShareholdingResponse:
    """查詢個股集保股權分散。"""
    with engine.connect() as conn:
        stock, from_, to = _resolve(conn, stock_id, from_, to, "shareholding")

        data = fetch_shareholding(conn, stock_id, from_, to, limit)

        items = []
        for item in data:
            levels = [
                ShareholdingLevel(
                    level=level["level"],
                    holders=level["holders"],
                    shares=level["shares"],
                    ratio=level["ratio"],
                )
                for level in item["levels"]
            ]
            items.append(
                ShareholdingWeek(
                    week=item["week_date"],
                    total_holders=item["total_holders"],
                    total_shares=item["total_shares"],
                    big_holder_ratio=item["big_holder_ratio"],
                    retail_ratio=item["retail_ratio"],
                    levels=levels,
                )
            )

        return ShareholdingResponse(
            stock_id=stock_id,
            name=stock["name"],
            market=stock["market"],
            from_=from_,
            to=to,
            count=len(items),
            items=items,
        )
