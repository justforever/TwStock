"""ETL 命令行介面。"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.exc import SQLAlchemyError

from twstock_db.config import get_database_url
from twstock_db.engine import get_engine
from twstock_etl.errors import SourceFormatError
from twstock_etl.jobs import refresh_stock_list, refresh_trading_calendar
from twstock_etl.scheduler import build_scheduler

logger = logging.getLogger(__name__)

TAIPEI = ZoneInfo("Asia/Taipei")


def main(argv: list[str] | None = None) -> int:
    """CLI 進入點。

    Args:
        argv: 命令行參數；為 None 時用 sys.argv[1:]

    Returns:
        exit code (0 = 成功，1 = 錯誤，2 = 參數錯誤)
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="TwStock ETL 工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # load-stocks 子指令
    load_stocks_parser = subparsers.add_parser("load-stocks", help="載入個股清單")
    load_stocks_parser.add_argument(
        "--market",
        required=True,
        choices=["TWSE", "TPEx"],
        help="市場別",
    )
    load_stocks_parser.add_argument(
        "--file",
        type=Path,
        help="本機 ISIN HTML 檔案路徑（UTF-8）",
    )
    load_stocks_parser.add_argument(
        "--deactivate-missing",
        action="store_true",
        help="停用清單中消失的個股",
    )

    # load-calendar 子指令
    load_calendar_parser = subparsers.add_parser("load-calendar", help="載入交易日曆")
    load_calendar_parser.add_argument(
        "--year",
        type=int,
        help="年份（預設：台北時間今年）",
    )
    load_calendar_parser.add_argument(
        "--file",
        type=Path,
        help="本機 JSON 檔案路徑（UTF-8）",
    )

    # scheduler 子指令
    subparsers.add_parser("scheduler", help="啟動排程器")

    args = parser.parse_args(argv)

    try:
        if args.command == "load-stocks":
            return _cmd_load_stocks(args)
        elif args.command == "load-calendar":
            return _cmd_load_calendar(args)
        elif args.command == "scheduler":
            return _cmd_scheduler()
    except (SourceFormatError, httpx.HTTPError, RuntimeError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except SQLAlchemyError as e:
        print(f"error: 資料庫錯誤：{e}", file=sys.stderr)
        return 1

    return 0


def _cmd_load_stocks(args: argparse.Namespace) -> int:
    """load-stocks 子指令實作。"""
    html = None
    if args.file:
        html = args.file.read_text(encoding="utf-8")

    engine = get_engine()
    result = refresh_stock_list(
        engine, args.market, html=html, deactivate=args.deactivate_missing
    )
    print(
        f"loaded market={result.market} records={result.records} "
        f"deactivated={result.deactivated}"
    )
    return 0


def _cmd_load_calendar(args: argparse.Namespace) -> int:
    """load-calendar 子指令實作。"""
    year = args.year
    if year is None:
        year = datetime.now(TAIPEI).year

    payload = None
    if args.file:
        import json
        payload = json.loads(args.file.read_text(encoding="utf-8"))

    engine = get_engine()
    result = refresh_trading_calendar(engine, year, payload=payload)
    print(
        f"loaded year={result.year} days={result.days} "
        f"open={result.open_days} closed={result.closed_days}"
    )
    return 0


def _cmd_scheduler() -> int:
    """scheduler 子指令實作。"""
    engine = get_engine()
    scheduler = build_scheduler(engine)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("排程器已停止")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
