"""ETL 命令行介面。"""

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.exc import SQLAlchemyError

from twstock_db.config import get_database_url
from twstock_db.engine import get_engine
from twstock_etl.backfill import (
    BackfillAborted,
    BackfillOptions,
    backfill_calendar,
    backfill_exright,
    backfill_index,
    backfill_prices,
    backfill_chip,
)
from twstock_etl.errors import SourceFormatError
from twstock_etl.jobs import (
    load_adj_factors,
    load_daily_price,
    load_index_month,
    load_shareholding,
    load_chip_daily,
    rebuild_calendar_from_index,
    refresh_stock_list,
    refresh_trading_calendar,
)
from twstock_etl.scheduler import build_scheduler

logger = logging.getLogger(__name__)

TAIPEI = ZoneInfo("Asia/Taipei")

BACKFILL_EPILOG = """建議順序（第一次回補 5 年）：
  1. python -m twstock_etl.cli load-stocks --market TWSE
  2. python -m twstock_etl.cli load-stocks --market TPEx
  3. python -m twstock_etl.cli load-calendar                      # 今年
  4. python -m twstock_etl.cli backfill index    --from 2021-01 --to 2026-09     # 約 60 次請求
  5. python -m twstock_etl.cli backfill calendar --from-year 2021 --to-year 2025 # 不發請求
  6. python -m twstock_etl.cli backfill price    --market TWSE --from 2021-01-04 --to 2026-09-18
  7. python -m twstock_etl.cli backfill price    --market TPEx --from 2021-01-04 --to 2026-09-18
  8. python -m twstock_etl.cli backfill exright  --from 2021-01-01 --to 2026-09-18
  9. python -m twstock_etl.cli backfill chip --kind institutional --market TWSE --from … --to …
  10. python -m twstock_etl.cli backfill chip --kind margin        --market TWSE --from … --to …

步驟 6、7 各約 1,200 次請求，--sleep 3 約需 1 小時。可以隨時 Ctrl-C，再執行會從中斷處繼續。
"""


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

    # load-price 子指令
    load_price_parser = subparsers.add_parser("load-price", help="載入日成交行情")
    load_price_parser.add_argument(
        "--market",
        required=True,
        choices=["TWSE", "TPEx"],
        help="市場別",
    )
    load_price_parser.add_argument(
        "--date",
        type=_parse_date,
        help="交易日（預設：台北時間今天）",
    )
    load_price_parser.add_argument(
        "--file",
        type=Path,
        help="本機 JSON 檔案路徑（UTF-8）",
    )
    load_price_parser.add_argument(
        "--force",
        action="store_true",
        help="強制重抓（跳過斷點續傳檢查）",
    )
    load_price_parser.add_argument(
        "--no-calendar-check",
        action="store_true",
        help="不檢查交易日曆",
    )

    # load-index 子指令
    load_index_parser = subparsers.add_parser("load-index", help="載入指數日 K")
    load_index_parser.add_argument(
        "--year",
        type=int,
        help="年份（預設：台北時間今年）",
    )
    load_index_parser.add_argument(
        "--month",
        type=int,
        help="月份 1-12（預設：台北時間本月）",
    )
    load_index_parser.add_argument(
        "--file",
        type=Path,
        help="本機 JSON 檔案路徑（UTF-8）",
    )
    load_index_parser.add_argument(
        "--force",
        action="store_true",
        help="強制重抓（跳過斷點續傳檢查）",
    )

    # load-exright 子指令
    load_exright_parser = subparsers.add_parser("load-exright", help="載入除權除息")
    load_exright_parser.add_argument(
        "--from",
        type=_parse_date,
        dest="start",
        help="起始日期（預設：最近 7 天前含今天）",
    )
    load_exright_parser.add_argument(
        "--to",
        type=_parse_date,
        dest="end",
        help="結束日期（預設：台北時間今天）",
    )
    load_exright_parser.add_argument(
        "--file",
        type=Path,
        help="本機 JSON 檔案路徑（UTF-8）",
    )
    load_exright_parser.add_argument(
        "--force",
        action="store_true",
        help="強制重抓（跳過斷點續傳檢查）",
    )

    # load-shareholding 子指令
    load_shareholding_parser = subparsers.add_parser(
        "load-shareholding", help="載入集保股權分散"
    )
    load_shareholding_parser.add_argument(
        "--file",
        type=Path,
        help="本機 CSV 檔案路徑（UTF-8）",
    )
    load_shareholding_parser.add_argument(
        "--force",
        action="store_true",
        help="強制重抓（跳過斷點續傳檢查）",
    )

    # load-chip 子指令
    load_chip_parser = subparsers.add_parser("load-chip", help="載入單日籌碼資料")
    load_chip_parser.add_argument(
        "--kind",
        required=True,
        choices=["institutional", "margin", "sbl", "foreign"],
        help="籌碼種類",
    )
    load_chip_parser.add_argument(
        "--market",
        required=True,
        choices=["TWSE", "TPEx"],
        help="市場別",
    )
    load_chip_parser.add_argument(
        "--date",
        type=_parse_date,
        help="交易日（預設：台北時間今天）",
    )
    load_chip_parser.add_argument(
        "--file",
        type=Path,
        help="本機 JSON 檔案路徑（UTF-8）",
    )
    load_chip_parser.add_argument(
        "--force",
        action="store_true",
        help="強制重抓（跳過斷點續傳檢查）",
    )
    load_chip_parser.add_argument(
        "--no-calendar-check",
        action="store_true",
        help="不檢查交易日曆",
    )

    # rebuild-calendar 子指令
    rebuild_calendar_parser = subparsers.add_parser(
        "rebuild-calendar", help="由指數反推交易日曆"
    )
    rebuild_calendar_parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="年份",
    )
    rebuild_calendar_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆蓋已有的日曆紀錄",
    )

    # backfill 子指令
    backfill_parser = subparsers.add_parser(
        "backfill",
        help="歷史資料回補（速率限制、斷點續傳、進度輸出）",
        epilog=BACKFILL_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    backfill_sub = backfill_parser.add_subparsers(dest="backfill_command", required=True)

    def _add_backfill_common_options(p: argparse.ArgumentParser) -> None:
        """為回補子指令加共用選項。"""
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

    # backfill price 子子指令
    price_parser = backfill_sub.add_parser("price", help="回補個股日 K")
    price_parser.add_argument(
        "--market",
        choices=["TWSE", "TPEx"],
        required=True,
        help="市場（TWSE 上市、TPEx 上櫃）",
    )
    price_parser.add_argument(
        "--from",
        type=_parse_date,
        required=True,
        dest="start",
        help="起始日期（YYYY-MM-DD，含）",
    )
    price_parser.add_argument(
        "--to",
        type=_parse_date,
        required=True,
        dest="end",
        help="結束日期（YYYY-MM-DD，含）",
    )
    _add_backfill_common_options(price_parser)

    # backfill index 子子指令
    index_parser = backfill_sub.add_parser("index", help="回補加權指數")
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
    _add_backfill_common_options(index_parser)

    # backfill exright 子子指令
    exright_parser = backfill_sub.add_parser("exright", help="回補除權息")
    exright_parser.add_argument(
        "--from",
        type=_parse_date,
        required=True,
        dest="start",
        help="起始日期（YYYY-MM-DD，含）",
    )
    exright_parser.add_argument(
        "--to",
        type=_parse_date,
        required=True,
        dest="end",
        help="結束日期（YYYY-MM-DD，含）",
    )
    _add_backfill_common_options(exright_parser)

    # backfill calendar 子子指令
    calendar_parser = backfill_sub.add_parser(
        "calendar", help="反推交易日曆（由指數推算）"
    )
    calendar_parser.add_argument(
        "--from-year", type=int, required=True, help="起始年份（含）"
    )
    calendar_parser.add_argument("--to-year", type=int, required=True, help="結束年份（含）")
    _add_backfill_common_options(calendar_parser)

    # backfill chip 子子指令
    chip_parser = backfill_sub.add_parser("chip", help="回補籌碼資料")
    chip_parser.add_argument(
        "--kind",
        required=True,
        choices=["institutional", "margin", "sbl", "foreign"],
        help="籌碼種類",
    )
    chip_parser.add_argument(
        "--market",
        required=True,
        choices=["TWSE", "TPEx"],
        help="市場別",
    )
    chip_parser.add_argument(
        "--from",
        type=_parse_date,
        required=True,
        dest="start",
        help="起始日期（YYYY-MM-DD，含）",
    )
    chip_parser.add_argument(
        "--to",
        type=_parse_date,
        required=True,
        dest="end",
        help="結束日期（YYYY-MM-DD，含）",
    )
    _add_backfill_common_options(chip_parser)

    # scheduler 子指令
    subparsers.add_parser("scheduler", help="啟動排程器")

    args = parser.parse_args(argv)

    try:
        if args.command == "load-stocks":
            return _cmd_load_stocks(args)
        elif args.command == "load-calendar":
            return _cmd_load_calendar(args)
        elif args.command == "load-price":
            return _cmd_load_price(args)
        elif args.command == "load-index":
            return _cmd_load_index(args)
        elif args.command == "load-exright":
            return _cmd_load_exright(args)
        elif args.command == "load-shareholding":
            return _cmd_load_shareholding(args)
        elif args.command == "load-chip":
            return _cmd_load_chip(args)
        elif args.command == "rebuild-calendar":
            return _cmd_rebuild_calendar(args)
        elif args.command == "backfill":
            return _cmd_backfill(args)
        elif args.command == "scheduler":
            return _cmd_scheduler()
    except (SourceFormatError, httpx.HTTPError, RuntimeError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except SQLAlchemyError as e:
        print(f"error: 資料庫錯誤：{e}", file=sys.stderr)
        return 1

    return 0


def _parse_date(value: str) -> date:
    """解析 YYYY-MM-DD 格式的日期。"""
    try:
        parts = value.split("-")
        if len(parts) != 3:
            raise ValueError
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        return date(year, month, day)
    except (ValueError, IndexError):
        raise argparse.ArgumentTypeError(f"日期格式錯誤：{value}，應為 YYYY-MM-DD")


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


def _cmd_load_price(args: argparse.Namespace) -> int:
    """load-price 子指令實作。"""
    trade_date = args.date
    if trade_date is None:
        trade_date = datetime.now(TAIPEI).date()

    payload = None
    if args.file:
        payload = json.loads(args.file.read_text(encoding="utf-8"))

    engine = get_engine()
    result = load_daily_price(
        engine,
        args.market,
        trade_date,
        payload=payload,
        check_calendar=not args.no_calendar_check,
        force=args.force,
    )

    if result.skip_reason is not None:
        print(f"skipped market={args.market} date={trade_date} reason={result.skip_reason}")
    else:
        print(
            f"loaded market={result.market} date={result.trade_date} "
            f"rows={result.rows} skipped_unknown={result.skipped_unknown}"
        )

    return 0


def _cmd_load_index(args: argparse.Namespace) -> int:
    """load-index 子指令實作。"""
    year = args.year
    if year is None:
        year = datetime.now(TAIPEI).year

    month = args.month
    if month is None:
        month = datetime.now(TAIPEI).month

    payload = None
    if args.file:
        payload = json.loads(args.file.read_text(encoding="utf-8"))

    engine = get_engine()
    result = load_index_month(
        engine, year, month, payload=payload, force=args.force
    )

    if result.skip_reason is not None:
        print(
            f"skipped index=TAIEX month={year:04d}-{month:02d} "
            f"reason={result.skip_reason}"
        )
    else:
        print(f"loaded index=TAIEX month={year:04d}-{month:02d} rows={result.rows}")

    return 0


def _cmd_load_exright(args: argparse.Namespace) -> int:
    """load-exright 子指令實作。"""
    now = datetime.now(TAIPEI).date()

    start = args.start
    if start is None:
        start = now - timedelta(days=7)

    end = args.end
    if end is None:
        end = now

    payload = None
    if args.file:
        payload = json.loads(args.file.read_text(encoding="utf-8"))

    engine = get_engine()
    result = load_adj_factors(engine, start, end, payload=payload, force=args.force)

    if result.skip_reason is not None:
        print(f"skipped exright from={start} to={end} reason={result.skip_reason}")
    else:
        print(f"loaded exright from={start} to={end} rows={result.rows}")

    return 0


def _cmd_load_shareholding(args: argparse.Namespace) -> int:
    """load-shareholding 子指令實作。"""
    csv_text = None
    if args.file:
        csv_text = args.file.read_text(encoding="utf-8")

    engine = get_engine()
    result = load_shareholding(engine, csv_text=csv_text, force=args.force)

    week = result.week_date.isoformat() if result.week_date else "-"
    if result.skip_reason is not None:
        print(f"skipped shareholding week={week} reason={result.skip_reason}")
    else:
        print(
            f"loaded shareholding week={week} rows={result.rows} "
            f"skipped_unknown={result.skipped_unknown}"
        )

    return 0


def _cmd_load_chip(args: argparse.Namespace) -> int:
    """load-chip 子指令實作。"""
    trade_date = args.date
    if trade_date is None:
        trade_date = datetime.now(TAIPEI).date()

    payload = None
    if args.file:
        payload = json.loads(args.file.read_text(encoding="utf-8"))

    engine = get_engine()

    try:
        result = load_chip_daily(
            engine,
            args.kind,
            args.market,
            trade_date,
            payload=payload,
            check_calendar=not args.no_calendar_check,
            force=args.force,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.skip_reason is not None:
        print(
            f"skipped kind={args.kind} market={args.market} date={trade_date} "
            f"reason={result.skip_reason}"
        )
    else:
        print(
            f"loaded kind={args.kind} market={args.market} date={trade_date} "
            f"rows={result.rows} skipped_unknown={result.skipped_unknown}"
        )

    return 0


def _cmd_rebuild_calendar(args: argparse.Namespace) -> int:
    """rebuild-calendar 子指令實作。"""
    engine = get_engine()
    result = rebuild_calendar_from_index(
        engine, args.year, overwrite=args.overwrite
    )
    print(
        f"rebuilt year={result.year} days={result.days} "
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


def _cmd_backfill(args: argparse.Namespace) -> int:
    """backfill 子指令實作；回傳碼 0 成功／1 有失敗／2 超過失敗上限／130 被 Ctrl-C 中斷。"""
    engine = get_engine()
    options = BackfillOptions(
        sleep_seconds=args.sleep,
        max_failures=args.max_failures,
        force=args.force,
        source_dir=args.source_dir,
        dry_run=args.dry_run,
    )

    try:
        if args.backfill_command == "price":
            summary = backfill_prices(engine, args.market, args.start, args.end, options)
        elif args.backfill_command == "index":
            summary = backfill_index(engine, args.start, args.end, options)
        elif args.backfill_command == "exright":
            summary = backfill_exright(engine, args.start, args.end, options)
        elif args.backfill_command == "calendar":
            summary = backfill_calendar(engine, args.from_year, args.to_year, options)
        elif args.backfill_command == "chip":
            summary = backfill_chip(engine, args.kind, args.market, args.start, args.end, options)
        else:
            return 1

        # 檢查結果
        if summary.interrupted_at:
            print(
                f"已中斷，下次執行會從 {summary.interrupted_at} 繼續", file=sys.stderr
            )
            return 130
        elif summary.failed > 0:
            return 1

        return 0

    except BackfillAborted as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
