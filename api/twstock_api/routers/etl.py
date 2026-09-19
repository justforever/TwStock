"""ETL 狀態 API 路由."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Engine

from twstock_api.deps import get_db_engine
from twstock_api.etl_repository import job_summary, recent_jobs
from twstock_api.schemas import EtlJobListResponse, EtlJobRun, EtlSummaryResponse

router = APIRouter(prefix="/api/etl", tags=["etl"])


@router.get("/jobs", response_model=EtlJobListResponse)
def get_etl_jobs(
    limit: int = Query(default=50, ge=1, le=500),
    engine: Engine = Depends(get_db_engine),
) -> EtlJobListResponse:
    """取得最近的 ETL 工作執行紀錄。"""
    with engine.connect() as conn:
        jobs = recent_jobs(conn, limit)

    items = []
    for job in jobs:
        items.append(
            EtlJobRun(
                job_id=job["job_id"],
                job_name=job["job_name"],
                target_date=job["target_date"],
                target_key=job["target_key"],
                status=job["status"],
                rows=job["rows"],
                error=job["error"],
                started_at=job["started_at"],
                finished_at=job["finished_at"],
                duration_seconds=job["duration_seconds"],
            )
        )

    return EtlJobListResponse(count=len(items), items=items)


@router.get("/summary", response_model=EtlSummaryResponse)
def get_etl_summary(
    engine: Engine = Depends(get_db_engine),
) -> EtlSummaryResponse:
    """取得 ETL 工作摘要。"""
    with engine.connect() as conn:
        summaries = job_summary(conn)

    items = []
    for summary in summaries:
        from twstock_api.schemas import EtlJobSummaryItem

        items.append(
            EtlJobSummaryItem(
                job_name=summary["job_name"],
                last_status=summary["last_status"],
                last_target_date=summary["last_target_date"],
                last_target_key=summary["last_target_key"],
                last_rows=summary["last_rows"],
                last_started_at=summary["last_started_at"],
                last_finished_at=summary["last_finished_at"],
                failed_last_7_days=summary["failed_last_7_days"],
                total_runs=summary["total_runs"],
            )
        )

    return EtlSummaryResponse(count=len(items), items=items)
