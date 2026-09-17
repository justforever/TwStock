"""ISIN 一覽表 parser 測試。"""

from datetime import date
from pathlib import Path

import pytest

from twstock_etl.errors import SourceFormatError
from twstock_etl.sources.isin import (
    decode_isin_bytes,
    parse_isin_html,
)


class TestDecodeISINBytes:
    """decode_isin_bytes 測試。"""

    def test_cp950_decode(self) -> None:
        """CP950 編碼解碼。"""
        # 台積電 (UTF-8: E5 8F B0 E7 A7 AF E9 9B BB)
        utf8_text = "台積電"
        cp950_bytes = utf8_text.encode("cp950")
        result = decode_isin_bytes(cp950_bytes)
        assert result == "台積電"

    def test_fallback_to_big5hkscs(self) -> None:
        """CP950 失敗時退到 big5hkscs。"""
        # 建造無法用 cp950 解碼的位元組
        # 一個 invalid utf-8 序列
        invalid_bytes = b"\x80\x81\x82"
        result = decode_isin_bytes(invalid_bytes)
        # 應該用 big5hkscs 且 errors='replace'
        assert isinstance(result, str)


class TestParseISINHTML:
    """parse_isin_html 測試。"""

    def test_parse_twse_fixture(self) -> None:
        """解析 TWSE fixture。"""
        fixture_path = Path(__file__).parent / "fixtures" / "isin_twse_strmode2.html"
        html = fixture_path.read_text(encoding="utf-8")

        records = parse_isin_html(html, "TWSE")

        assert len(records) == 9
        # 驗證順序：1101, 2317, 2330, 2834, 2881, 6415, 0050, 0056, 00878
        assert records[0].stock_id == "1101"
        assert records[1].stock_id == "2317"
        assert records[2].stock_id == "2330"
        assert records[3].stock_id == "2834"
        assert records[4].stock_id == "2881"
        assert records[5].stock_id == "6415"
        assert records[6].stock_id == "0050"
        assert records[7].stock_id == "0056"
        assert records[8].stock_id == "00878"

    def test_parse_twse_record_fields(self) -> None:
        """驗證 2330 詳細欄位。"""
        fixture_path = Path(__file__).parent / "fixtures" / "isin_twse_strmode2.html"
        html = fixture_path.read_text(encoding="utf-8")

        records = parse_isin_html(html, "TWSE")
        record_2330 = next(r for r in records if r.stock_id == "2330")

        assert record_2330.name == "台積電"
        assert record_2330.industry == "半導體業"
        assert record_2330.listed_date == date(1994, 9, 5)
        assert record_2330.is_etf is False
        assert record_2330.isin_code == "TW0002330008"
        assert record_2330.cfi_code == "ESVUFR"

    def test_parse_twse_etf(self) -> None:
        """驗證 ETF（0050）。"""
        fixture_path = Path(__file__).parent / "fixtures" / "isin_twse_strmode2.html"
        html = fixture_path.read_text(encoding="utf-8")

        records = parse_isin_html(html, "TWSE")
        record_0050 = next(r for r in records if r.stock_id == "0050")

        assert record_0050.is_etf is True
        assert record_0050.industry is None

    def test_parse_skips_non_stock_sections(self) -> None:
        """驗證跳過非股票區段（權證、特別股、TDR）。"""
        fixture_path = Path(__file__).parent / "fixtures" / "isin_twse_strmode2.html"
        html = fixture_path.read_text(encoding="utf-8")

        records = parse_isin_html(html, "TWSE")
        codes = {r.stock_id for r in records}

        # 應該不含權證、特別股、TDR
        assert "030001" not in codes  # 權證
        assert "2881A" not in codes   # 特別股
        assert "9105" not in codes    # TDR

    def test_parse_name_with_symbols(self) -> None:
        """驗證名稱含特殊符號（如 * - ）。"""
        fixture_path = Path(__file__).parent / "fixtures" / "isin_twse_strmode2.html"
        html = fixture_path.read_text(encoding="utf-8")

        records = parse_isin_html(html, "TWSE")
        record_6415 = next(r for r in records if r.stock_id == "6415")

        # 名稱應為 "矽力*-KY"，不要改為 "矽力-KY" 或其他
        assert record_6415.name == "矽力*-KY"

        # 驗證 2834 是 "臺企銀"，不改為 "台企銀"
        record_2834 = next(r for r in records if r.stock_id == "2834")
        assert record_2834.name == "臺企銀"

    def test_parse_tpex_fixture(self) -> None:
        """解析 TPEx fixture。"""
        fixture_path = Path(__file__).parent / "fixtures" / "isin_tpex_strmode4.html"
        html = fixture_path.read_text(encoding="utf-8")

        records = parse_isin_html(html, "TPEx")

        assert len(records) == 8
        # 驗證順序：3105, 4966, 5347, 5483, 6488, 8069, 006201, 00679B
        assert records[0].stock_id == "3105"
        assert records[-1].stock_id == "00679B"
        assert records[-1].is_etf is True

        # 全部應為 TPEx
        for r in records:
            assert r.market == "TPEx"

    def test_parse_empty_raises(self) -> None:
        """空 HTML 應拋出 SourceFormatError。"""
        with pytest.raises(SourceFormatError):
            parse_isin_html("<html></html>", "TWSE")

    def test_parse_invalid_market_raises(self) -> None:
        """無效市場應拋 ValueError。"""
        with pytest.raises(ValueError):
            parse_isin_html("<html></html>", "XYZ")

    def test_parse_bad_rows_skipped(self) -> None:
        """格式錯誤的列應被跳過。"""
        html = """
        <html><body><table>
        <tr><td colspan=1>股票</td></tr>
        <tr><td colspan=7>2330　台積電</td><td>TW0002330008</td><td></td><td></td><td>半導體業</td><td>ESVUFR</td><td></td></tr>
        <tr><td colspan=7>2330台積電</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
        <tr><td colspan=7>23-0　壞</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
        </table></body></html>
        """

        records = parse_isin_html(html, "TWSE")

        # 只應有 1 筆（第一筆正常的）
        assert len(records) == 1
        assert records[0].stock_id == "2330"

    def test_parse_invalid_listed_date_keeps_row(self) -> None:
        """無效上市日期應設為 None，但保留該列。"""
        html = """
        <html><body><table>
        <tr><td colspan=1>股票</td></tr>
        <tr><td colspan=7>2330　台積電</td><td>TW0002330008</td><td>2026/13/40</td><td></td><td>半導體業</td><td>ESVUFR</td><td></td></tr>
        </table></body></html>
        """

        records = parse_isin_html(html, "TWSE")

        assert len(records) == 1
        assert records[0].stock_id == "2330"
        assert records[0].listed_date is None

    def test_parse_halfwidth_space_fallback(self) -> None:
        """半形空白（無全形空白）也能解析。"""
        html = """
        <html><body><table>
        <tr><td colspan=1>股票</td></tr>
        <tr><td colspan=7>2330 台積電</td><td>TW0002330008</td><td></td><td></td><td>半導體業</td><td>ESVUFR</td><td></td></tr>
        </table></body></html>
        """

        records = parse_isin_html(html, "TWSE")

        assert len(records) == 1
        assert records[0].stock_id == "2330"
        assert records[0].name == "台積電"

    def test_decode_isin_bytes_cp950(self) -> None:
        """驗證 CP950 編碼路徑。"""
        fixture_path = Path(__file__).parent / "fixtures" / "isin_twse_strmode2.html"
        utf8_text = fixture_path.read_text(encoding="utf-8")

        # 轉成 CP950 位元組再解碼
        cp950_bytes = utf8_text.encode("cp950")
        result = decode_isin_bytes(cp950_bytes)

        # 應該能還原出相同的文本
        records_from_utf8 = parse_isin_html(utf8_text, "TWSE")
        records_from_cp950 = parse_isin_html(result, "TWSE")

        assert len(records_from_utf8) == len(records_from_cp950)
        for r1, r2 in zip(records_from_utf8, records_from_cp950):
            assert r1.stock_id == r2.stock_id
            assert r1.name == r2.name
