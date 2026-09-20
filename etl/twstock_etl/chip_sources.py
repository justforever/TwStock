"""籌碼來源登錄表：把 kind × market 對應到 fetch / parse / upsert 與 job 名稱。"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

import httpx
from sqlalchemy import Connection

from twstock_etl.loaders.chip import (
    upsert_foreign_holding,
    upsert_institutional,
    upsert_margin,
    upsert_sbl,
)
from twstock_etl.loaders.price import PriceUpsertResult
from twstock_etl.sources.institutional import (
    fetch_tpex_institutional,
    fetch_twse_institutional,
    parse_tpex_institutional,
    parse_twse_institutional,
)
from twstock_etl.sources.margin import (
    fetch_tpex_margin,
    fetch_twse_margin,
    parse_tpex_margin,
    parse_twse_margin,
)
from twstock_etl.sources.twse_foreign import (
    fetch_twse_foreign_holding,
    parse_twse_foreign_holding,
)
from twstock_etl.sources.twse_sbl import fetch_twse_sbl, parse_twse_sbl


@dataclass(frozen=True)
class ChipSource:
    """一個籌碼來源（一種資料 × 一個市場）。"""

    kind: str  # institutional / margin / sbl / foreign
    market: str  # TWSE / TPEx
    job_name: str  # 見規格 §4
    label: str  # 中文說明，給 log 與 CLI 用，例「上市三大法人」
    fetch: Callable[[date, httpx.Client | None], dict]
    parse: Callable[[dict, date], list]
    upsert: Callable[[Connection, Sequence], PriceUpsertResult]


CHIP_KINDS: tuple[str, ...] = ("institutional", "margin", "sbl", "foreign")

CHIP_SOURCES: dict[tuple[str, str], ChipSource] = {
    ("institutional", "TWSE"): ChipSource(
        "institutional",
        "TWSE",
        "institutional_twse",
        "上市三大法人",
        fetch_twse_institutional,
        parse_twse_institutional,
        upsert_institutional,
    ),
    ("institutional", "TPEx"): ChipSource(
        "institutional",
        "TPEx",
        "institutional_tpex",
        "上櫃三大法人",
        fetch_tpex_institutional,
        parse_tpex_institutional,
        upsert_institutional,
    ),
    ("margin", "TWSE"): ChipSource(
        "margin",
        "TWSE",
        "margin_twse",
        "上市融資融券",
        fetch_twse_margin,
        parse_twse_margin,
        upsert_margin,
    ),
    ("margin", "TPEx"): ChipSource(
        "margin",
        "TPEx",
        "margin_tpex",
        "上櫃融資融券",
        fetch_tpex_margin,
        parse_tpex_margin,
        upsert_margin,
    ),
    ("sbl", "TWSE"): ChipSource(
        "sbl",
        "TWSE",
        "sbl_twse",
        "上市借券賣出",
        fetch_twse_sbl,
        parse_twse_sbl,
        upsert_sbl,
    ),
    ("foreign", "TWSE"): ChipSource(
        "foreign",
        "TWSE",
        "foreign_holding_twse",
        "上市外資持股",
        fetch_twse_foreign_holding,
        parse_twse_foreign_holding,
        upsert_foreign_holding,
    ),
}


def get_chip_source(kind: str, market: str) -> ChipSource:
    """取得指定籌碼來源。

    Raises:
        ValueError: 這個 kind × market 組合不存在（例如上櫃借券，M2 沒有來源）
    """
    if (kind, market) not in CHIP_SOURCES:
        available = ", ".join(f"{k}/{m}" for k, m in CHIP_SOURCES)
        raise ValueError(
            f"沒有這個籌碼來源：kind={kind} market={market}；可用組合：{available}"
        )
    return CHIP_SOURCES[(kind, market)]
