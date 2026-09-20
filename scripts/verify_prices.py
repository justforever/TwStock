#!/usr/bin/env python3
"""驗證 M1 的 API 回傳值符合 fixture 手算預期。"""

import argparse
import sys
from typing import Any
import urllib.request
import json


def fetch_json(url: str) -> Any:
    """從 HTTP 端點取得 JSON。"""
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())


def main(argv: list[str] | None = None) -> int:
    """驗證 M1 的 API 回傳值符合 fixture 手算預期。"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--api-base',
        default='http://127.0.0.1:18001',
        help='API 基址（預設：http://127.0.0.1:18001）',
    )
    args = parser.parse_args(argv)

    base = args.api_base.rstrip('/')
    checks = []
    passed = 0
    failed = 0

    # 檢查 1: raw-close
    try:
        resp = fetch_json(f"{base}/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18")
        if resp['count'] == 3 and [c['close'] for c in resp['items']] == [
            1000.0,
            995.0,
            1008.0,
        ]:
            print('OK raw-close')
            passed += 1
        else:
            closes = [c['close'] for c in resp['items']]
            print(f"FAIL raw-close {closes}")
            failed += 1
    except Exception as e:
        print(f"FAIL raw-close {e}")
        failed += 1

    # 檢查 2: adjusted-close
    try:
        resp = fetch_json(
            f"{base}/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18&adj=true"
        )
        if [c['close'] for c in resp['items']] == [990.0, 995.0, 1008.0]:
            if resp['items'][0]['open'] == 985.05:
                print('OK adjusted-close')
                passed += 1
            else:
                print(f"FAIL adjusted-close open={resp['items'][0]['open']}")
                failed += 1
        else:
            closes = [c['close'] for c in resp['items']]
            print(f"FAIL adjusted-close {closes}")
            failed += 1
    except Exception as e:
        print(f"FAIL adjusted-close {e}")
        failed += 1

    # 檢查 3: adjusted-flag
    try:
        resp_adj = fetch_json(
            f"{base}/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18&adj=true"
        )
        resp_raw = fetch_json(f"{base}/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18")
        if resp_adj['adjusted'] and not resp_raw['adjusted']:
            print('OK adjusted-flag')
            passed += 1
        else:
            print(f"FAIL adjusted-flag adj={resp_adj['adjusted']}")
            failed += 1
    except Exception as e:
        print(f"FAIL adjusted-flag {e}")
        failed += 1

    # 檢查 4: volume-not-adjusted
    try:
        resp = fetch_json(
            f"{base}/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18&adj=true"
        )
        if resp['items'][0]['volume'] == 25000000:
            print('OK volume-not-adjusted')
            passed += 1
        else:
            print(f"FAIL volume-not-adjusted {resp['items'][0]['volume']}")
            failed += 1
    except Exception as e:
        print(f"FAIL volume-not-adjusted {e}")
        failed += 1

    # 檢查 5: stock-detail
    try:
        resp = fetch_json(f"{base}/api/stocks/2330")
        if resp['name'] == '台積電' and resp['latest']['close'] == 1008.0:
            print('OK stock-detail')
            passed += 1
        else:
            print(f"FAIL stock-detail name={resp.get('name')}")
            failed += 1
    except Exception as e:
        print(f"FAIL stock-detail {e}")
        failed += 1

    # 檢查 6: tpex-price
    try:
        resp = fetch_json(f"{base}/api/stocks/3105/prices?from=2026-09-16&to=2026-09-18")
        if resp['count'] == 3 and resp['items'][-1]['close'] == 349.0:
            print('OK tpex-price')
            passed += 1
        else:
            closes = [c['close'] for c in resp['items']]
            print(f"FAIL tpex-price {closes}")
            failed += 1
    except Exception as e:
        print(f"FAIL tpex-price {e}")
        failed += 1

    # 檢查 7: index
    try:
        resp = fetch_json(f"{base}/api/indices/TAIEX/prices?from=2026-09-16&to=2026-09-18")
        if resp['count'] == 3 and resp['items'][-1]['close'] == 24780.0:
            print('OK index')
            passed += 1
        else:
            closes = [c['close'] for c in resp['items']]
            print(f"FAIL index {closes}")
            failed += 1
    except Exception as e:
        print(f"FAIL index {e}")
        failed += 1

    # 檢查 8: etl-summary
    try:
        resp = fetch_json(f"{base}/api/etl/summary")
        job_names = {item['job_name'] for item in resp['items']}
        required = {
            'daily_price_twse',
            'daily_price_tpex',
            'index_daily_taiex',
            'adj_factor_twse',
        }
        if required.issubset(job_names):
            if all(
                item['last_status'] == 'success'
                for item in resp['items']
                if item['job_name'] in required
            ):
                print('OK etl-summary')
                passed += 1
            else:
                print(f"FAIL etl-summary status mismatch")
                failed += 1
        else:
            print(f"FAIL etl-summary missing jobs {required - job_names}")
            failed += 1
    except Exception as e:
        print(f"FAIL etl-summary {e}")
        failed += 1

    # 檢查 9: unknown-stock
    try:
        urllib.request.urlopen(f"{base}/api/stocks/9999/prices")
        print('FAIL unknown-stock expected 404')
        failed += 1
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print('OK unknown-stock')
            passed += 1
        else:
            print(f'FAIL unknown-stock expected 404, got {e.code}')
            failed += 1
    except Exception as e:
        print(f'FAIL unknown-stock {e}')
        failed += 1

    if failed == 0:
        print(f"OK all {passed} price checks passed")
        return 0
    else:
        print(f"FAILED {failed}/{passed + failed}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
