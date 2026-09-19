"""回補腳本核心邏輯。"""

import io
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from textwrap import dedent
from typing import Callable, TextIO
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import Engine, select
from sqlalchemy.exc import DBAPIError

from twstock_db.tables import trading_calendar
from twstock_etl.errors import SourceFormatError
from twstock_etl.jobs import (
    load_adj_factors,
    load_daily_price,
    load_index_month,
    rebuild_calendar_from_index,
)
from twstock_etl.loaders.job_log import has_successful_run, job_run

logger = logging.getLogger(__name__)

DEFAULT_SLEEP_SECONDS = 3.0
DEFAULT_MAX_FAILURES = 10
TAIPEI = ZoneInfo("Asia/Taipei")


class BackfillAborted(Exception):
    """回補因失敗次數超過上限而中止。"""

    pass


class RateLimiter:
    """確保兩次請求之間至少間隔 min_interval 秒。"""

    def __init__(
        self,
        min_interval: float,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """初始化速率限制器。

        Args:
            min_interval: 兩次請求之間的最小間隔（秒）
            sleep: 睡眠函式（方便測試注入假實現）
            clock: 時鐘函式（方便測試注入假實現）
        """
        self.min_interval = min_interval
        self.sleep = sleep
        self.clock = clock
        self.last_wait_time: float | None = None

    def wait(self) -> None:
        """必要時睡到距離上次 wait() 已滿 min_interval 秒。"""
        now = self.clock()
        if self.last_wait_time is not None:
            elapsed = now - self.last_wait_time
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                self.sleep(sleep_time)
        self.last_wait_time = self.clock()


@dataclass(frozen=True)
class BackfillOptions:
    """回補共用選項。"""

    sleep_seconds: float = DEFAULT_SLEEP_SECONDS
    max_failures: int = DEFAULT_MAX_FAILURES
    force: bool = False
    source_dir: Path | None = None  # 離線模式：從目錄讀 JSON，不發 HTTP
    dry_run: bool = False  # 只印要做什麼，不寫 DB、不發 HTTP
    out: TextIO = field(default_factory=lambda: sys.stdout)


@dataclass
class BackfillSummary:
    """回補結果統計。"""

    total: int
    done: int
    skipped: int
    failed: int
    rows: int
    interrupted_at: str | None = None  # 被 Ctrl-C 中斷時，下次該從哪裡續跑


def trading_days(engine: Engine, start: date, end: date) -> list[date]:
    """從 trading_calendar 取出區間內 is_open=true 的日期（升冪）。

    日曆完全沒有涵蓋到這個區間時 raise SourceFormatError，
    訊息提示「請先執行 load-calendar 或 backfill calendar」。
    """
    with engine.begin() as conn:
        result = conn.execute(
            select(trading_calendar.c.trade_date)
            .where(
                (trading_calendar.c.trade_date >= start)
                & (trading_calendar.c.trade_date <= end)
                & (trading_calendar.c.is_open == True)
            )
            .order_by(trading_calendar.c.trade_date)
        )
        days = [row.trade_date for row in result]

    if not days:
        raise SourceFormatError(
            f"交易日曆中 {start} 到 {end} 完全沒有開市日，"
            f"請先執行 load-calendar 或 backfill calendar"
        )

    return days


def _format_time(seconds: float) -> str:
    """格式化秒數為 HH:MM:SS。"""
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _progress_line(
    index: int,
    total: int,
    name: str,
    rows: int | None = None,
    skip_reason: str | None = None,
    fail_msg: str | None = None,
    dry_run: bool = False,
    elapsed: float | None = None,
    eta: float | None = None,
) -> str:
    """產生進度行。

    格式範例：
    - 成功：[  12/1250] 2021-01-20 TWSE rows=1024 elapsed=00:00:38 eta=01:02:15
    - 跳過：[  12/1250] 2021-01-20 TWSE skip 已完成
    - 失敗：[  13/1250] 2021-01-21 TWSE FAIL 錯誤訊息
    - dry-run：[  12/1250] 2021-01-20 TWSE dry-run

    Args:
        index: 目前工作單位編號（1-based）
        total: 總工作單位數
        name: 該單位的名稱字串（如日期或年月）
        rows: 寫入筆數（成功時）
        skip_reason: 跳過原因（跳過時）
        fail_msg: 失敗訊息（失敗時）
        dry_run: 是否為 dry-run
        elapsed: 耗時（秒）
        eta: 預計還要多久（秒，或 None 表示 --:--:--)
    """
    line = f"[{index:>4d}/{total:>4d}] {name}"

    if skip_reason is not None:
        line += f" skip {skip_reason}"
    elif fail_msg is not None:
        line += f" FAIL {fail_msg}"
    elif dry_run:
        line += " dry-run"
    elif rows is not None:
        line += f" rows={rows}"
        if elapsed is not None:
            line += f" elapsed={_format_time(elapsed)}"
        if eta is not None:
            line += f" eta={_format_time(eta)}"
        else:
            line += " eta=--:--:--"

    return line


def backfill_prices(
    engine: Engine,
    market: str,
    start: date,
    end: date,
    options: BackfillOptions,
) -> BackfillSummary:
    """逐交易日回補 daily_price。"""
    days = trading_days(engine, start, end)
    total = len(days)

    summary = BackfillSummary(total=total, done=0, skipped=0, failed=0, rows=0)
    start_time = datetime.now(TAIPEI)
    limiter = RateLimiter(
        options.sleep_seconds
        if options.source_dir is None
        else 0  # 離線模式不用等待
    )

    try:
        for i, day in enumerate(days, start=1):
            try:
                # 檢查斷點續傳
                with engine.begin() as conn:
                    if (
                        not options.force
                        and has_successful_run(
                            conn, f"daily_price_{market.lower()}", target_date=day
                        )
                    ):
                        summary.skipped += 1
                        print(
                            _progress_line(
                                i,
                                total,
                                day.isoformat(),
                                skip_reason="已完成",
                            ),
                            file=options.out,
                            flush=True,
                        )
                        continue

                # 如果是 dry-run，只印不執行
                if options.dry_run:
                    print(
                        _progress_line(
                            i,
                            total,
                            day.isoformat(),
                            dry_run=True,
                        ),
                        file=options.out,
                        flush=True,
                    )
                    summary.done += 1
                    continue

                # 限制速率（只在發 HTTP 前）
                if options.source_dir is None:
                    limiter.wait()

                # 執行 job
                payload = None
                if options.source_dir is not None:
                    # 離線模式：從檔案讀 JSON
                    file_name = f"{market}_price_{day.strftime('%Y%m%d')}.json"
                    file_path = options.source_dir / file_name
                    try:
                        import json
                        with open(file_path) as f:
                            payload = json.load(f)
                    except FileNotFoundError:
                        raise FileNotFoundError(f"檔案不存在：{file_path}")

                result = load_daily_price(engine, market, day, payload=payload)
                summary.done += 1
                summary.rows += result.rows

                # 印進度
                elapsed = (datetime.now(TAIPEI) - start_time).total_seconds()
                avg_time = elapsed / summary.done
                remaining = (total - i) * avg_time

                print(
                    _progress_line(
                        i,
                        total,
                        day.isoformat(),
                        rows=result.rows,
                        elapsed=elapsed,
                        eta=remaining,
                    ),
                    file=options.out,
                    flush=True,
                )

            except Exception as exc:
                summary.failed += 1
                error_msg = str(exc).split("\n")[0]  # 只取第一行

                print(
                    _progress_line(
                        i,
                        total,
                        day.isoformat(),
                        fail_msg=error_msg,
                    ),
                    file=options.out,
                    flush=True,
                )

                if summary.failed > options.max_failures:
                    summary.interrupted_at = day.isoformat()
                    raise BackfillAborted(
                        f"失敗次數超過 {options.max_failures}，中止回補"
                    )

    except KeyboardInterrupt:
        summary.interrupted_at = days[len(days) - (total - i)].isoformat()
        logger.info("被使用者中斷")

    elapsed = (datetime.now(TAIPEI) - start_time).total_seconds()
    print(
        f"完成 {summary.done}／跳過 {summary.skipped}／失敗 {summary.failed}，"
        f"共寫入 {summary.rows} 筆，耗時 {_format_time(elapsed)}",
        file=options.out,
        flush=True,
    )

    return summary


def backfill_index(
    engine: Engine,
    start_month: str,
    end_month: str,
    options: BackfillOptions,
) -> BackfillSummary:
    """逐月回補 index_daily（start_month / end_month 格式 'YYYY-MM'）。"""
    start_date = datetime.strptime(start_month, "%Y-%m").date()
    end_date = datetime.strptime(end_month, "%Y-%m").date()

    # 生成所有月份
    months = []
    current = start_date.replace(day=1)
    while current <= end_date:
        months.append(current.strftime("%Y-%m"))
        # 移至下一個月
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    total = len(months)
    summary = BackfillSummary(total=total, done=0, skipped=0, failed=0, rows=0)
    start_time = datetime.now(TAIPEI)
    limiter = RateLimiter(
        options.sleep_seconds
        if options.source_dir is None
        else 0  # 離線模式不用等待
    )

    try:
        for i, month_str in enumerate(months, start=1):
            try:
                # 檢查斷點續傳
                with engine.begin() as conn:
                    if (
                        not options.force
                        and has_successful_run(conn, "index_daily_taiex", target_key=month_str)
                    ):
                        summary.skipped += 1
                        print(
                            _progress_line(
                                i,
                                total,
                                month_str,
                                skip_reason="已完成",
                            ),
                            file=options.out,
                            flush=True,
                        )
                        continue

                # 如果是 dry-run，只印不執行
                if options.dry_run:
                    print(
                        _progress_line(
                            i,
                            total,
                            month_str,
                            dry_run=True,
                        ),
                        file=options.out,
                        flush=True,
                    )
                    summary.done += 1
                    continue

                # 限制速率（只在發 HTTP 前）
                if options.source_dir is None:
                    limiter.wait()

                # 執行 job
                year, month = int(month_str[:4]), int(month_str[5:7])
                payload = None
                if options.source_dir is not None:
                    # 離線模式：從檔案讀 JSON
                    file_name = f"TAIEX_index_{month_str.replace('-', '')}.json"
                    file_path = options.source_dir / file_name
                    try:
                        import json
                        with open(file_path) as f:
                            payload = json.load(f)
                    except FileNotFoundError:
                        raise FileNotFoundError(f"檔案不存在：{file_path}")

                result = load_index_month(engine, year, month, payload=payload)
                summary.done += 1
                summary.rows += result.rows

                # 印進度
                elapsed = (datetime.now(TAIPEI) - start_time).total_seconds()
                avg_time = elapsed / summary.done
                remaining = (total - i) * avg_time

                print(
                    _progress_line(
                        i,
                        total,
                        month_str,
                        rows=result.rows,
                        elapsed=elapsed,
                        eta=remaining,
                    ),
                    file=options.out,
                    flush=True,
                )

            except Exception as exc:
                summary.failed += 1
                error_msg = str(exc).split("\n")[0]  # 只取第一行

                print(
                    _progress_line(
                        i,
                        total,
                        month_str,
                        fail_msg=error_msg,
                    ),
                    file=options.out,
                    flush=True,
                )

                if summary.failed > options.max_failures:
                    summary.interrupted_at = month_str
                    raise BackfillAborted(
                        f"失敗次數超過 {options.max_failures}，中止回補"
                    )

    except KeyboardInterrupt:
        summary.interrupted_at = months[len(months) - (total - i)]
        logger.info("被使用者中斷")

    elapsed = (datetime.now(TAIPEI) - start_time).total_seconds()
    print(
        f"完成 {summary.done}／跳過 {summary.skipped}／失敗 {summary.failed}，"
        f"共寫入 {summary.rows} 筆，耗時 {_format_time(elapsed)}",
        file=options.out,
        flush=True,
    )

    return summary


def backfill_exright(
    engine: Engine,
    start: date,
    end: date,
    options: BackfillOptions,
) -> BackfillSummary:
    """逐月回補 adj_factor（每次請求一個自然月）。"""
    # 生成所有月份
    months = []
    current = start.replace(day=1)
    while current <= end:
        month_start = current
        if current.month == 12:
            month_end = date(current.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(current.year, current.month + 1, 1) - timedelta(days=1)
        months.append((month_start, month_end))
        # 移至下一個月
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    # 截至 end
    months = [(s, min(e, end)) for s, e in months]

    total = len(months)
    summary = BackfillSummary(total=total, done=0, skipped=0, failed=0, rows=0)
    start_time = datetime.now(TAIPEI)
    limiter = RateLimiter(
        options.sleep_seconds
        if options.source_dir is None
        else 0  # 離線模式不用等待
    )

    try:
        for i, (month_start, month_end) in enumerate(months, start=1):
            try:
                target_key = f"{month_start.strftime('%Y%m%d')}-{month_end.strftime('%Y%m%d')}"

                # 檢查斷點續傳
                with engine.begin() as conn:
                    if (
                        not options.force
                        and has_successful_run(conn, "adj_factor_twse", target_key=target_key)
                    ):
                        summary.skipped += 1
                        print(
                            _progress_line(
                                i,
                                total,
                                target_key,
                                skip_reason="已完成",
                            ),
                            file=options.out,
                            flush=True,
                        )
                        continue

                # 如果是 dry-run，只印不執行
                if options.dry_run:
                    print(
                        _progress_line(
                            i,
                            total,
                            target_key,
                            dry_run=True,
                        ),
                        file=options.out,
                        flush=True,
                    )
                    summary.done += 1
                    continue

                # 限制速率（只在發 HTTP 前）
                if options.source_dir is None:
                    limiter.wait()

                # 執行 job
                payload = None
                if options.source_dir is not None:
                    # 離線模式：從檔案讀 JSON
                    file_name = f"exright_{month_start.strftime('%Y%m%d')}_{month_end.strftime('%Y%m%d')}.json"
                    file_path = options.source_dir / file_name
                    try:
                        import json
                        with open(file_path) as f:
                            payload = json.load(f)
                    except FileNotFoundError:
                        raise FileNotFoundError(f"檔案不存在：{file_path}")

                result = load_adj_factors(engine, month_start, month_end, payload=payload)
                summary.done += 1
                summary.rows += result.rows

                # 印進度
                elapsed = (datetime.now(TAIPEI) - start_time).total_seconds()
                avg_time = elapsed / summary.done
                remaining = (total - i) * avg_time

                print(
                    _progress_line(
                        i,
                        total,
                        target_key,
                        rows=result.rows,
                        elapsed=elapsed,
                        eta=remaining,
                    ),
                    file=options.out,
                    flush=True,
                )

            except Exception as exc:
                summary.failed += 1
                error_msg = str(exc).split("\n")[0]  # 只取第一行

                print(
                    _progress_line(
                        i,
                        total,
                        target_key,
                        fail_msg=error_msg,
                    ),
                    file=options.out,
                    flush=True,
                )

                if summary.failed > options.max_failures:
                    summary.interrupted_at = target_key
                    raise BackfillAborted(
                        f"失敗次數超過 {options.max_failures}，中止回補"
                    )

    except KeyboardInterrupt:
        idx = len(months) - (total - i)
        if idx >= 0:
            summary.interrupted_at = f"{months[idx][0].strftime('%Y%m%d')}-{months[idx][1].strftime('%Y%m%d')}"
        logger.info("被使用者中斷")

    elapsed = (datetime.now(TAIPEI) - start_time).total_seconds()
    print(
        f"完成 {summary.done}／跳過 {summary.skipped}／失敗 {summary.failed}，"
        f"共寫入 {summary.rows} 筆，耗時 {_format_time(elapsed)}",
        file=options.out,
        flush=True,
    )

    return summary


def backfill_calendar(
    engine: Engine,
    from_year: int,
    to_year: int,
    options: BackfillOptions,
) -> BackfillSummary:
    """用已回補的 TAIEX 指數反推歷史年度交易日曆（不發 HTTP）。"""
    years = list(range(from_year, to_year + 1))
    total = len(years)

    summary = BackfillSummary(total=total, done=0, skipped=0, failed=0, rows=0)
    start_time = datetime.now(TAIPEI)

    try:
        for i, year in enumerate(years, start=1):
            try:
                target_key = f"{year:04d}"

                # 檢查斷點續傳
                with engine.begin() as conn:
                    if (
                        not options.force
                        and has_successful_run(conn, "calendar_from_index", target_key=target_key)
                    ):
                        summary.skipped += 1
                        print(
                            _progress_line(
                                i,
                                total,
                                target_key,
                                skip_reason="已完成",
                            ),
                            file=options.out,
                            flush=True,
                        )
                        continue

                # 如果是 dry-run，只印不執行
                if options.dry_run:
                    print(
                        _progress_line(
                            i,
                            total,
                            target_key,
                            dry_run=True,
                        ),
                        file=options.out,
                        flush=True,
                    )
                    summary.done += 1
                    continue

                # 執行 job（不需要速率限制，不發 HTTP）
                result = rebuild_calendar_from_index(engine, year)
                summary.done += 1
                summary.rows += result.days

                # 印進度
                elapsed = (datetime.now(TAIPEI) - start_time).total_seconds()
                avg_time = elapsed / summary.done
                remaining = (total - i) * avg_time

                print(
                    _progress_line(
                        i,
                        total,
                        target_key,
                        rows=result.days,
                        elapsed=elapsed,
                        eta=remaining,
                    ),
                    file=options.out,
                    flush=True,
                )

            except Exception as exc:
                summary.failed += 1
                error_msg = str(exc).split("\n")[0]  # 只取第一行

                print(
                    _progress_line(
                        i,
                        total,
                        target_key,
                        fail_msg=error_msg,
                    ),
                    file=options.out,
                    flush=True,
                )

                if summary.failed > options.max_failures:
                    summary.interrupted_at = target_key
                    raise BackfillAborted(
                        f"失敗次數超過 {options.max_failures}，中止回補"
                    )

    except KeyboardInterrupt:
        idx = len(years) - (total - i)
        if idx >= 0:
            summary.interrupted_at = f"{years[idx]:04d}"
        logger.info("被使用者中斷")

    elapsed = (datetime.now(TAIPEI) - start_time).total_seconds()
    print(
        f"完成 {summary.done}／跳過 {summary.skipped}／失敗 {summary.failed}，"
        f"共寫入 {summary.rows} 筆，耗時 {_format_time(elapsed)}",
        file=options.out,
        flush=True,
    )

    return summary
