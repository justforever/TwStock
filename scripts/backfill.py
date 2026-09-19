#!/usr/bin/env python3
"""TwStock 歷史資料回補工具。用法見 --help。"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# 添加 etl 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "etl"))

from twstock_db.engine import get_engine
from twstock_etl.backfill import (
    BackfillAborted,
    BackfillOptions,
    backfill_calendar,
    backfill_exright,
    backfill_index,
    backfill_prices,
)
from twstock_etl.errors import SourceFormatError

TAIPEI = ZoneInfo("Asia/Taipei")

HELP_EPILOG = """建議順序（第一次回補 5 年）：
  1. python -m twstock_etl.cli load-stocks --market TWSE
  2. python -m twstock_etl.cli load-stocks --market TPEx
  3. python -m twstock_etl.cli load-calendar                      # 今年
  4. scripts/backfill.py index    --from 2021-01 --to 2026-09     # 約 60 次請求
  5. scripts/backfill.py calendar --from-year 2021 --to-year 2025 # 不發請求
  6. scripts/backfill.py price    --market TWSE --from 2021-01-04 --to 2026-09-18
  7. scripts/backfill.py price    --market TPEx --from 2021-01-04 --to 2026-09-18
  8. scripts/backfill.py exright  --from 2021-01-01 --to 2026-09-18

步驟 6、7 各約 1,200 次請求，--sleep 3 約需 1 小時。可以隨時 Ctrl-C，再執行會從中斷處繼續。
"""


def main() -> int:
    """主程式。"""
    parser = argparse.ArgumentParser(
        description="TwStock 歷史資料回補工具",
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="子指令")

    # 共用選項工廠函數
    def add_common_options(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--sleep",
            type=float,
            default=3.0,
            help="兩次請求間隔（秒），預設 3.0",
        )
        p.add_argument(
            "--force",
            action="store_true",
            help="強制重新抓取，不使用斷點續傳",
        )
        p.add_argument(
            "--source-dir",
            type=Path,
            help="離線模式：從指定目錄讀 JSON，不發 HTTP",
        )
        p.add_argument(
            "--dry-run",
            action="store_true",
            help="只印要做什麼，不寫 DB、不發 HTTP",
        )
        p.add_argument(
            "--max-failures",
            type=int,
            default=10,
            help="最多容許失敗次數，預設 10",
        )

    # price 子指令
    price_parser = subparsers.add_parser(
        "price", help="回補個股日 K", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    price_parser.add_argument(
        "--market",
        choices=["TWSE", "TPEx"],
        required=True,
        help="市場（TWSE 上市、TPEx 上櫃）",
    )
    price_parser.add_argument(
        "--from",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        required=True,
        dest="start",
        help="起始日期（YYYY-MM-DD，含）",
    )
    price_parser.add_argument(
        "--to",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        required=True,
        dest="end",
        help="結束日期（YYYY-MM-DD，含）",
    )
    add_common_options(price_parser)

    # index 子指令
    index_parser = subparsers.add_parser(
        "index", help="回補加權指數", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    index_parser.add_argument(
        "--from",
        required=True,
        dest="start",
        help="起始年月（YYYY-MM，含）",
    )
    index_parser.add_argument(
        "--to",
        required=True,
        dest="end",
        help="結束年月（YYYY-MM，含）",
    )
    add_common_options(index_parser)

    # exright 子指令
    exright_parser = subparsers.add_parser(
        "exright", help="回補除權息", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    exright_parser.add_argument(
        "--from",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        required=True,
        dest="start",
        help="起始日期（YYYY-MM-DD，含）",
    )
    exright_parser.add_argument(
        "--to",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        required=True,
        dest="end",
        help="結束日期（YYYY-MM-DD，含）",
    )
    add_common_options(exright_parser)

    # calendar 子指令
    calendar_parser = subparsers.add_parser(
        "calendar",
        help="反推交易日曆（由指數推算）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    calendar_parser.add_argument(
        "--from-year", type=int, required=True, help="起始年份（含）"
    )
    calendar_parser.add_argument("--to-year", type=int, required=True, help="結束年份（含）")
    add_common_options(calendar_parser)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # 設定 logging
    logging.basicConfig(level=logging.WARNING)

    # 讀環境變數建 engine
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("錯誤：未設定 DATABASE_URL 環境變數", file=sys.stderr)
        return 1

    engine = get_engine(database_url)

    # 組建 BackfillOptions
    options = BackfillOptions(
        sleep_seconds=args.sleep,
        max_failures=args.max_failures,
        force=args.force,
        source_dir=args.source_dir,
        dry_run=args.dry_run,
    )

    try:
        if args.command == "price":
            summary = backfill_prices(engine, args.market, args.start, args.end, options)
        elif args.command == "index":
            summary = backfill_index(engine, args.start, args.end, options)
        elif args.command == "exright":
            summary = backfill_exright(engine, args.start, args.end, options)
        elif args.command == "calendar":
            summary = backfill_calendar(engine, args.from_year, args.to_year, options)
        else:
            parser.print_help()
            return 1

        # 檢查結果
        if summary.interrupted_at:
            print(f"已中斷，下次執行會從 {summary.interrupted_at} 繼續", file=sys.stderr)
            return 130
        elif summary.failed > 0:
            return 1

        return 0

    except BackfillAborted as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (SourceFormatError, FileNotFoundError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
