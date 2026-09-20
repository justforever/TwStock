#!/usr/bin/env python3
"""籌碼資料 API 驗收腳本。

用法：
    scripts/verify_chips.py --api-base http://127.0.0.1:18002
"""
import argparse
import json
import sys
import urllib.request
from typing import Any


def fetch_json(api_base: str, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    """從 API 抓 JSON。"""
    url = f"{api_base}{path}"
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query_string}"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status == 404:
                return {"status": 404}
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": 404}
        raise


def main():
    """執行驗收。"""
    parser = argparse.ArgumentParser(description="籌碼資料 API 驗收")
    parser.add_argument("--api-base", default="http://127.0.0.1:18002", help="API 基底 URL")
    args = parser.parse_args()

    tests = []
    failures = []

    # Test 1: 三大法人三天升冪
    try:
        data = fetch_json(args.api_base, "/api/stocks/2330/institutional",
                         {"from": "2026-09-16", "to": "2026-09-18"})
        if (data.get("count") == 3 and
            [i["foreign_net"] for i in data.get("items", [])] == [5000000, 8000000, 12000000]):
            print("OK inst-series 三天資料升冪且 foreign_net 正確")
            tests.append("inst-series")
        else:
            print(f"FAIL inst-series count={data.get('count')} foreign_nets={[i['foreign_net'] for i in data.get('items', [])]}")
            failures.append("inst-series")
    except Exception as e:
        print(f"FAIL inst-series {e}")
        failures.append("inst-series")

    # Test 2: 三大法人詳細
    try:
        data = fetch_json(args.api_base, "/api/stocks/2330/institutional",
                         {"from": "2026-09-16", "to": "2026-09-18"})
        last = data.get("items", [{}])[-1]
        if (last.get("foreign_buy") == 30000000 and
            last.get("foreign_sell") == 18000000 and
            last.get("trust_net") == 2000000 and
            last.get("dealer_net") == -500000 and
            last.get("total_net") == 13500000):
            print("OK inst-detail 最後一筆欄位正確")
            tests.append("inst-detail")
        else:
            print(f"FAIL inst-detail {last}")
            failures.append("inst-detail")
    except Exception as e:
        print(f"FAIL inst-detail {e}")
        failures.append("inst-detail")

    # Test 3: 融資券三天升冪
    try:
        data = fetch_json(args.api_base, "/api/stocks/2330/margin",
                         {"from": "2026-09-16", "to": "2026-09-18"})
        margin_balances = [i["margin_balance"] for i in data.get("items", [])]
        short_balances = [i["short_balance"] for i in data.get("items", [])]
        if (margin_balances == [19500000, 20000000, 20200000] and
            short_balances == [900000, 1000000, 1090000]):
            print("OK margin-series 融資融券餘額正確")
            tests.append("margin-series")
        else:
            print(f"FAIL margin-series margin={margin_balances} short={short_balances}")
            failures.append("margin-series")
    except Exception as e:
        print(f"FAIL margin-series {e}")
        failures.append("margin-series")

    # Test 4: 借券賣出
    try:
        data = fetch_json(args.api_base, "/api/stocks/2330/margin",
                         {"from": "2026-09-16", "to": "2026-09-18"})
        last = data.get("items", [{}])[-1]
        first = data.get("items", [{}])[0]
        if (last.get("sbl_sell") == 300000 and
            last.get("sbl_balance") == 4500000 and
            first.get("sbl_sell") is None):
            print("OK margin-sbl 借券正確（有 upsert 部分欄位）")
            tests.append("margin-sbl")
        else:
            print(f"FAIL margin-sbl last={last} first={first}")
            failures.append("margin-sbl")
    except Exception as e:
        print(f"FAIL margin-sbl {e}")
        failures.append("margin-sbl")

    # Test 5: 融資券比例
    try:
        data = fetch_json(args.api_base, "/api/stocks/2330/margin",
                         {"from": "2026-09-16", "to": "2026-09-18"})
        last = data.get("items", [{}])[-1]
        if last.get("margin_ratio") == 5.396:
            print("OK margin-ratio 融券比例正確")
            tests.append("margin-ratio")
        else:
            print(f"FAIL margin-ratio {last.get('margin_ratio')}")
            failures.append("margin-ratio")
    except Exception as e:
        print(f"FAIL margin-ratio {e}")
        failures.append("margin-ratio")

    # Test 6: 外資持股
    try:
        data = fetch_json(args.api_base, "/api/stocks/2330/foreign-holding")
        if (data.get("count") == 1 and
            data.get("items", [{}])[0].get("holding_shares") == 18151266320 and
            data.get("items", [{}])[0].get("holding_ratio") == 70.0 and
            data.get("items", [{}])[0].get("available_ratio") == 30.0):
            print("OK foreign-holding 外資持股正確")
            tests.append("foreign-holding")
        else:
            print(f"FAIL foreign-holding {data}")
            failures.append("foreign-holding")
    except Exception as e:
        print(f"FAIL foreign-holding {e}")
        failures.append("foreign-holding")

    # Test 7: 集保股權分散
    try:
        data = fetch_json(args.api_base, "/api/stocks/2330/shareholding")
        item = data.get("items", [{}])[0] if data.get("items") else {}
        if (data.get("count") == 1 and
            item.get("big_holder_ratio") == 80.0 and
            item.get("retail_ratio") == 20.0 and
            item.get("total_holders") == 1000000 and
            item.get("total_shares") == 1000000000 and
            len(item.get("levels", [])) == 7):
            print("OK shareholding 集保股權分散正確")
            tests.append("shareholding")
        else:
            print(f"FAIL shareholding {item}")
            failures.append("shareholding")
    except Exception as e:
        print(f"FAIL shareholding {e}")
        failures.append("shareholding")

    # Test 8: 上櫃三大法人
    try:
        data = fetch_json(args.api_base, "/api/stocks/3105/institutional")
        last = data.get("items", [{}])[-1] if data.get("items") else {}
        if (last.get("foreign_net") == 550000 and
            last.get("total_net") == 630000):
            print("OK tpex-inst 上櫃三大法人正確")
            tests.append("tpex-inst")
        else:
            print(f"FAIL tpex-inst {last}")
            failures.append("tpex-inst")
    except Exception as e:
        print(f"FAIL tpex-inst {e}")
        failures.append("tpex-inst")

    # Test 9: 區間內無資料
    try:
        data = fetch_json(args.api_base, "/api/stocks/2330/institutional",
                         {"from": "2020-01-01", "to": "2020-01-31"})
        if data.get("count") == 0 and data.get("items") == []:
            print("OK empty-range 區間無資料正確")
            tests.append("empty-range")
        else:
            print(f"FAIL empty-range count={data.get('count')} items={data.get('items')}")
            failures.append("empty-range")
    except Exception as e:
        print(f"FAIL empty-range {e}")
        failures.append("empty-range")

    # Test 10: 個股不存在
    try:
        data = fetch_json(args.api_base, "/api/stocks/9999/institutional")
        if data.get("status") == 404:
            print("OK unknown-stock 個股不存在回 404")
            tests.append("unknown-stock")
        else:
            print(f"FAIL unknown-stock {data}")
            failures.append("unknown-stock")
    except Exception as e:
        print(f"FAIL unknown-stock {e}")
        failures.append("unknown-stock")

    # Summary
    print()
    if not failures:
        print("OK all 10 chip checks passed")
        return 0
    else:
        print(f"FAILED {len(tests)}/10")
        return 1


if __name__ == "__main__":
    sys.exit(main())
