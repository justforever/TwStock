"""TWSE 休市日 parser 測試。"""

import json
from datetime import date
from pathlib import Path

import pytest

from twstock_etl.errors import SourceFormatError
from twstock_etl.sources.twse_holiday import (
    build_calendar,
    parse_holiday_schedule,
)


class TestParseHolidaySchedule:
    """parse_holiday_schedule 測試。"""

    def test_parse_fixture(self) -> None:
        """解析 fixture。"""
        fixture_path = Path(__file__).parent / "fixtures" / "twse_holiday_schedule_2026.json"
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        holidays = parse_holiday_schedule(data)

        assert len(holidays) == 15

        # 驗證 1150102 是 is_trading_day=True
        trading_day_holiday = next(h for h in holidays if h.holiday_date == date(2026, 1, 2))
        assert trading_day_holiday.is_trading_day is True

        # 驗證 1150101 是 is_trading_day=False
        rest_holiday = next(h for h in holidays if h.holiday_date == date(2026, 1, 1))
        assert rest_holiday.is_trading_day is False

    def test_parse_missing_name_raises(self) -> None:
        """缺 Name 鍵。"""
        data = [{"Date": "1150101", "Description": ""}]

        with pytest.raises(SourceFormatError):
            parse_holiday_schedule(data)

    def test_parse_missing_date_raises(self) -> None:
        """缺 Date 鍵。"""
        data = [{"Name": "test", "Description": ""}]

        with pytest.raises(SourceFormatError):
            parse_holiday_schedule(data)

    def test_parse_bad_date_raises(self) -> None:
        """日期無效。"""
        data = [{"Name": "test", "Date": "abc"}]

        with pytest.raises(SourceFormatError):
            parse_holiday_schedule(data)

    def test_parse_empty_list(self) -> None:
        """空陣列應返回空 list。"""
        holidays = parse_holiday_schedule([])
        assert holidays == []


class TestBuildCalendar:
    """build_calendar 測試。"""

    def test_build_calendar_counts(self) -> None:
        """驗證 2026 年的開市/休市天數。"""
        fixture_path = Path(__file__).parent / "fixtures" / "twse_holiday_schedule_2026.json"
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        holidays = parse_holiday_schedule(data)
        calendar = build_calendar(2026, holidays)

        assert len(calendar) == 365

        open_days = sum(1 for d in calendar if d.is_open)
        rest_days = sum(1 for d in calendar if not d.is_open)

        assert open_days == 250
        assert rest_days == 115

    def test_build_calendar_specific_days(self) -> None:
        """驗證特定日期。"""
        fixture_path = Path(__file__).parent / "fixtures" / "twse_holiday_schedule_2026.json"
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        holidays = parse_holiday_schedule(data)
        calendar = build_calendar(2026, holidays)

        # 建立查詢字典
        cal_dict = {d.trade_date: d for d in calendar}

        # 2026-01-01 休市（中華民國開國紀念日）
        assert cal_dict[date(2026, 1, 1)].is_open is False
        assert cal_dict[date(2026, 1, 1)].note == "中華民國開國紀念日"

        # 2026-01-02 開市（開始交易日）
        assert cal_dict[date(2026, 1, 2)].is_open is True
        assert cal_dict[date(2026, 1, 2)].note is None

        # 2026-01-03 休市（週末）
        assert cal_dict[date(2026, 1, 3)].is_open is False
        assert cal_dict[date(2026, 1, 3)].note == "週末"

        # 2026-02-11 開市（平日）
        assert cal_dict[date(2026, 2, 11)].is_open is True

        # 2026-02-12 休市（結算交割）
        assert cal_dict[date(2026, 2, 12)].is_open is False

        # 2026-02-28 休市（和平紀念日，假日優先於週末）
        assert cal_dict[date(2026, 2, 28)].is_open is False
        assert cal_dict[date(2026, 2, 28)].note == "和平紀念日"

    def test_build_calendar_wrong_year_raises(self) -> None:
        """請求不同年份的日曆。"""
        fixture_path = Path(__file__).parent / "fixtures" / "twse_holiday_schedule_2026.json"
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        holidays = parse_holiday_schedule(data)

        with pytest.raises(SourceFormatError, match="休市日資料不含"):
            build_calendar(2025, holidays)

    def test_build_calendar_leap_year(self) -> None:
        """閏年日曆。"""
        # 2028 是閏年
        holidays = [
            parse_holiday_schedule([{"Name": "test", "Date": "1170101", "Description": ""}])[0],
        ]

        calendar = build_calendar(2028, holidays)

        assert len(calendar) == 366
