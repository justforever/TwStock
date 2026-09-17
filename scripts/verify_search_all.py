#!/usr/bin/env python3
"""驗證 API 能以代號與名稱搜尋到 fixture 內的每一檔個股。"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import httpx
from twstock_etl.sources.isin import parse_isin_html


def main(argv: list[str] | None = None) -> int:
    """對 fixture 內每一檔個股，驗證 API 能以代號與名稱搜尋到。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:18000", help="API 基礎 URL")
    parser.add_argument("--twse-file", required=True, help="TWSE ISIN HTML 檔案路徑")
    parser.add_argument("--tpex-file", required=True, help="TPEx ISIN HTML 檔案路徑")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # 解析 fixture
    twse_html = Path(args.twse_file).read_text(encoding="utf-8")
    tpex_html = Path(args.tpex_file).read_text(encoding="utf-8")

    twse_records = parse_isin_html(twse_html, "TWSE")
    tpex_records = parse_isin_html(tpex_html, "TPEx")

    all_records = twse_records + tpex_records
    total = len(all_records)
    failures = []

    # 驗證每一筆
    with httpx.Client(base_url=args.api_base, timeout=10) as client:
        for record in all_records:
            # 用代號搜尋
            try:
                resp = client.get("/api/stocks", params={"q": record.stock_id, "limit": 100})
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])
                if not items or items[0]["stock_id"] != record.stock_id or items[0]["market"] != record.market:
                    failures.append(f"FAIL {record.stock_id} 代號搜尋失敗或市場不符")
            except Exception as e:
                failures.append(f"FAIL {record.stock_id} 代號搜尋異常: {e}")

            # 用名稱搜尋
            try:
                resp = client.get("/api/stocks", params={"q": record.name, "limit": 100})
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])
                found = any(item["stock_id"] == record.stock_id for item in items)
                if not found:
                    failures.append(f"FAIL {record.stock_id} 名稱搜尋未找到")
            except Exception as e:
                failures.append(f"FAIL {record.stock_id} 名稱搜尋異常: {e}")

    # 輸出結果
    for failure in failures:
        print(failure)

    if failures:
        print(f"FAILED {len(failures)}/{total}")
        return 1
    else:
        print(f"OK {total}/{total} stocks searchable by id and name")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
