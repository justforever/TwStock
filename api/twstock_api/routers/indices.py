"""指數價格 API 路由."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from twstock_api.deps import get_db_engine
from twstock_api.price_repository import (
    DEFAULT_LIMIT,
    DEFAULT_WINDOW_DAYS,
    INDEX_NAMES,
    MAX_LIMIT,
    fetch_index_prices,
)
from twstock_api.schemas import IndexBar, IndexResponse

router = APIRouter(prefix="/api/indices", tags=["indices"])


@router.get("/{index_id}/prices", response_model=IndexResponse)
def get_index_prices(
    index_id: str,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    engine: Engine = Depends(get_db_engine),
) -> IndexResponse:
    """查詢指數日 K。"""
    # 正規化 index_id
    index_id_upper = index_id.upper()

    # 驗證 index_id
    if index_id_upper not in INDEX_NAMES:
        raise HTTPException(status_code=404, detail=f"查無此指數：{index_id}")

    with engine.connect() as conn:
        # 決定 to 日期
        if to is None:
            # 查指數最新交易日
            from sqlalchemy import text

            sql = text("""
                SELECT MAX(trade_date) as latest_date
                FROM index_daily
                WHERE index_id = :index_id
            """)
            result = conn.execute(sql, {"index_id": index_id_upper}).fetchone()
            latest_date = result[0] if result and result[0] else None

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

        # 取得指數日 K
        bars = fetch_index_prices(conn, index_id_upper, from_, to, limit)

        # 轉換為 IndexBar
        items = []
        for bar in bars:
            items.append(
                IndexBar(
                    time=bar["trade_date"],
                    open=float(bar["open"]) if bar["open"] is not None else None,
                    high=float(bar["high"]) if bar["high"] is not None else None,
                    low=float(bar["low"]) if bar["low"] is not None else None,
                    close=float(bar["close"]) if bar["close"] is not None else None,
                )
            )

        return IndexResponse(
            index_id=index_id_upper,
            name=INDEX_NAMES[index_id_upper],
            from_=from_,
            to=to,
            count=len(items),
            items=items,
        )
