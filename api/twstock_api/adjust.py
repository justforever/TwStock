"""還原價格計算模組."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Sequence
from datetime import date

PRICE_FIELDS = ("open", "high", "low", "close", "change")
QUANT = Decimal("0.0001")


def cumulative_factors(
    bars: Sequence[dict[str, Any]], factors: Sequence[tuple[date, Decimal]]
) -> list[Decimal]:
    """對每根 K 棒算出「其後所有除權息係數的乘積」。

    bars 必須依 trade_date 升冪；factors 為 (ex_date, factor) 且依 ex_date 升冪。
    第 i 根 K 棒的係數 = Π{ f | ex_date > bars[i]["trade_date"] }。

    Returns:
        與 bars 等長的 Decimal 清單
    """
    idx = len(factors) - 1
    cum = Decimal(1)
    out: list[Decimal] = [Decimal(1)] * len(bars)
    for i in range(len(bars) - 1, -1, -1):
        while idx >= 0 and factors[idx][0] > bars[i]["trade_date"]:
            cum *= factors[idx][1]
            idx -= 1
        out[i] = cum
    return out


def apply_adjustment(
    bars: Sequence[dict[str, Any]], factors: Sequence[tuple[date, Decimal]]
) -> list[dict[str, Any]]:
    """回傳套用還原係數後的新 K 棒清單（不修改輸入）。

    只調整 PRICE_FIELDS，值為 None 就維持 None；
    結果 quantize 到 QUANT（ROUND_HALF_UP）。volume / turnover / transactions 不調整。
    """
    cum_factors = cumulative_factors(bars, factors)
    result = []
    for i, bar in enumerate(bars):
        adjusted_bar = dict(bar)
        factor = cum_factors[i]
        for field in PRICE_FIELDS:
            if field in adjusted_bar and adjusted_bar[field] is not None:
                adjusted_bar[field] = (
                    (Decimal(str(adjusted_bar[field])) * factor).quantize(QUANT, rounding=ROUND_HALF_UP)
                )
        result.append(adjusted_bar)
    return result
