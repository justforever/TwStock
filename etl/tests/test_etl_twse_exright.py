"""除權除息 parser 單元測試。"""

import json
import pathlib
from datetime import date
from decimal import Decimal

import pytest

from twstock_etl.sources.twse_exright import parse_exright

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestParseExright:
    """測試 parse_exright 函式。"""

    def test_parse_complete_fixture(self) -> None:
        """應正確解析完整 fixture。"""
        payload = json.loads((FIXTURE_DIR / "exright_20260901_20260930.json").read_text())
        records = parse_exright(payload)

        # 應有 2 筆（2317 的 prev_close=0 被跳過）
        assert len(records) == 2

        # 2330 的檢驗
        exr_2330 = next(r for r in records if r.stock_id == "2330")
        assert exr_2330.ex_date == date(2026, 9, 17)
        assert exr_2330.factor == Decimal("0.99000000")
        assert exr_2330.kind == "除息"
        assert exr_2330.source == "TWSE"

        # 1101 的檢驗
        exr_1101 = next(r for r in records if r.stock_id == "1101")
        assert exr_1101.ex_date == date(2026, 9, 16)
        assert exr_1101.factor == Decimal("0.99447514")

    def test_sorted_by_date_and_code(self) -> None:
        """應按 (ex_date, stock_id) 升冪排序。"""
        payload = json.loads((FIXTURE_DIR / "exright_20260901_20260930.json").read_text())
        records = parse_exright(payload)

        # 檢驗排序：1101 在 2330 之前
        assert records[0].stock_id == "1101"
        assert records[1].stock_id == "2330"

    def test_empty_result_allowed(self) -> None:
        """全部被跳過應回傳空 list（不報錯）。"""
        payload = json.loads((FIXTURE_DIR / "exright_20260901_20260930.json").read_text())
        # 把所有 prev_close 和 reference_price 設為 0
        for row in payload["data"]:
            row[3] = "0"  # prev_close
            row[4] = "0"  # reference_price

        records = parse_exright(payload)
        assert records == []
