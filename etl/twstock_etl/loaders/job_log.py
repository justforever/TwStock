"""ETL 工作日誌寫入 loader。"""

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator, NoReturn

from sqlalchemy import Engine, select, text
from sqlalchemy.exc import SQLAlchemyError

from twstock_db.tables import etl_job_log

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 2000


class JobSkipped(Exception):
    """job 在執行中決定跳過（非開市日、已完成等），由 job_run 攔下並記為 skipped。"""


@dataclass
class JobRun:
    """一次 job 執行的可變狀態，由 job_run() yield 出來。"""

    job_id: int
    job_name: str
    rows: int = 0  # 呼叫端執行完把筆數寫回來
    note: str | None = None  # 跳過原因，寫進 error 欄位

    def skip(self, reason: str) -> NoReturn:
        """中止此次 job 並記為 skipped。"""
        raise JobSkipped(reason)


@contextmanager
def job_run(
    engine: Engine,
    job_name: str,
    *,
    target_date: date | None = None,
    target_key: str | None = None,
) -> Iterator[JobRun]:
    """以 etl_job_log 包住一次 job 執行。

    進入時插入 status='running' 的一列（獨立交易，立即 commit）。
    正常結束 → status='success'、rows、finished_at=now()。
    拋 JobSkipped → status='skipped'、error=跳過原因、finished_at=now()，**不往外拋**。
    拋其他例外 → status='failed'、error=str(exc)[:MAX_ERROR_LENGTH]、finished_at=now()，**往外重拋**。
    """
    # 插入 running 狀態的紀錄
    with engine.begin() as conn:
        stmt = etl_job_log.insert().values(
            job_name=job_name,
            target_date=target_date,
            target_key=target_key,
            status="running",
        )
        result = conn.execute(stmt)
        job_id = result.inserted_primary_key[0]

    run = JobRun(job_id=job_id, job_name=job_name)

    try:
        yield run
        # 正常結束：記錄成功
        with engine.begin() as conn:
            conn.execute(
                etl_job_log.update()
                .where(etl_job_log.c.job_id == job_id)
                .values(status="success", rows=run.rows, finished_at=text("now()"))
            )
    except JobSkipped as exc:
        # 跳過：記錄跳過理由，不往外拋
        run.note = str(exc)
        with engine.begin() as conn:
            conn.execute(
                etl_job_log.update()
                .where(etl_job_log.c.job_id == job_id)
                .values(status="skipped", error=run.note, finished_at=text("now()"))
            )
    except Exception as exc:
        # 失敗：記錄錯誤訊息並重拋
        error_msg = str(exc)[: MAX_ERROR_LENGTH]
        with engine.begin() as conn:
            conn.execute(
                etl_job_log.update()
                .where(etl_job_log.c.job_id == job_id)
                .values(status="failed", error=error_msg, finished_at=text("now()"))
            )
        raise


def has_successful_run(
    conn,
    job_name: str,
    *,
    target_date: date | None = None,
    target_key: str | None = None,
) -> bool:
    """該 job 的該目標是否已有 status 為 success 或 skipped 的紀錄。"""
    stmt = select(etl_job_log).where(
        (etl_job_log.c.job_name == job_name)
        & (etl_job_log.c.target_date == target_date)
        & (etl_job_log.c.target_key == target_key)
        & (etl_job_log.c.status.in_(["success", "skipped"]))
    )
    result = conn.execute(stmt).first()
    return result is not None


def latest_run(conn, job_name: str) -> dict[str, Any] | None:
    """回傳該 job_name 最近一次執行的紀錄 dict；沒有回傳 None。"""
    stmt = (
        select(etl_job_log)
        .where(etl_job_log.c.job_name == job_name)
        .order_by(etl_job_log.c.started_at.desc())
        .limit(1)
    )
    result = conn.execute(stmt).first()
    if result is None:
        return None
    return dict(result._mapping)
