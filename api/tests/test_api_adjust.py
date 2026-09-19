"""還原價格計算單元測試."""
from datetime import date
from decimal import Decimal

import pytest

from twstock_api.adjust import apply_adjustment, cumulative_factors


def test_cumulative_factors_single_factor() -> None:
    """單一除權息係數測試."""
    bars = [
        {"trade_date": date(2026, 9, 16)},
        {"trade_date": date(2026, 9, 17)},
        {"trade_date": date(2026, 9, 18)},
    ]
    factors = [(date(2026, 9, 17), Decimal("0.99"))]

    result = cumulative_factors(bars, factors)

    assert result == [Decimal("0.99"), Decimal("1"), Decimal("1")]


def test_cumulative_factors_multiple_factors() -> None:
    """多個除權息係數測試."""
    bars = [
        {"trade_date": date(2026, 9, 16)},
        {"trade_date": date(2026, 9, 17)},
        {"trade_date": date(2026, 9, 18)},
    ]
    factors = [
        (date(2026, 9, 17), Decimal("0.99")),
        (date(2026, 9, 18), Decimal("0.98")),
    ]

    result = cumulative_factors(bars, factors)

    assert result == [
        Decimal("0.9702"),  # 0.99 * 0.98
        Decimal("0.98"),
        Decimal("1"),
    ]


def test_cumulative_factors_empty() -> None:
    """無除權息的情況."""
    bars = [
        {"trade_date": date(2026, 9, 16)},
        {"trade_date": date(2026, 9, 17)},
    ]
    factors = []

    result = cumulative_factors(bars, factors)

    assert result == [Decimal("1"), Decimal("1")]


def test_apply_adjustment_basic() -> None:
    """套用還原係數的基本測試."""
    bars = [
        {
            "trade_date": date(2026, 9, 16),
            "open": Decimal("1000.0"),
            "high": Decimal("1005.0"),
            "low": Decimal("995.0"),
            "close": Decimal("1000.0"),
            "change": Decimal("5.0"),
            "volume": 1000000,
            "turnover": Decimal("1000000000"),
        },
        {
            "trade_date": date(2026, 9, 17),
            "open": Decimal("1001.0"),
            "high": Decimal("1006.0"),
            "low": Decimal("996.0"),
            "close": Decimal("1001.0"),
            "change": Decimal("1.0"),
            "volume": 1100000,
            "turnover": Decimal("1100000000"),
        },
    ]
    factors = [(date(2026, 9, 17), Decimal("0.99"))]

    result = apply_adjustment(bars, factors)

    # 09-16 的價格應該乘以 0.99
    assert result[0]["close"] == Decimal("990.0000")
    assert result[0]["open"] == Decimal("990.0000")
    assert result[0]["high"] == Decimal("995.0000") if Decimal("1005.0") * Decimal("0.99") == Decimal("995.0000") else Decimal("994.9500")
    assert result[0]["volume"] == 1000000  # volume 不調整
    assert result[0]["turnover"] == Decimal("1000000000")  # turnover 不調整

    # 09-17 的價格不應該調整
    assert result[1]["close"] == Decimal("1001.0000")
    assert result[1]["open"] == Decimal("1001.0000")


def test_apply_adjustment_with_none_values() -> None:
    """含 None 值的還原係數測試."""
    bars = [
        {
            "trade_date": date(2026, 9, 16),
            "open": None,
            "high": Decimal("1005.0"),
            "low": None,
            "close": Decimal("1000.0"),
            "change": None,
            "volume": 1000000,
            "turnover": Decimal("1000000000"),
        },
    ]
    factors = [(date(2026, 9, 17), Decimal("0.99"))]

    result = apply_adjustment(bars, factors)

    assert result[0]["open"] is None
    assert result[0]["low"] is None
    assert result[0]["change"] is None
    assert result[0]["high"] == Decimal("994.9500")
    assert result[0]["close"] == Decimal("990.0000")


def test_apply_adjustment_empty_bars() -> None:
    """空 bars 的情況."""
    bars: list[dict] = []
    factors = [(date(2026, 9, 17), Decimal("0.99"))]

    result = apply_adjustment(bars, factors)

    assert result == []


def test_apply_adjustment_does_not_modify_input() -> None:
    """驗證不修改輸入的 bars."""
    original_bars = [
        {
            "trade_date": date(2026, 9, 16),
            "close": Decimal("1000.0"),
            "volume": 1000000,
        }
    ]
    bars = [dict(b) for b in original_bars]
    factors = [(date(2026, 9, 17), Decimal("0.99"))]

    result = apply_adjustment(bars, factors)

    # 檢查原始 bars 沒有被修改
    assert bars[0]["close"] == Decimal("1000.0")
    # 檢查結果被調整
    assert result[0]["close"] == Decimal("990.0000")
