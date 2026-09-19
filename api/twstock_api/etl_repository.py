"""ETL 日誌資料庫查詢模組."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


def recent_jobs(conn: Connection, limit: int) -> list[dict[str, Any]]:
    """最近的 etl_job_log，依 started_at 降冪。"""
    sql = text("""
        SELECT
            job_id, job_name, target_date, target_key,
            status, rows, error, started_at, finished_at,
            EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_seconds
        FROM etl_job_log
        ORDER BY started_at DESC, job_id DESC
        LIMIT :limit
    """)
    rows = conn.execute(sql, {"limit": limit}).fetchall()
    result = []
    for row in rows:
        d = dict(row._mapping)
        # Convert None to None for duration_seconds
        if d["finished_at"] is None:
            d["duration_seconds"] = None
        else:
            d["duration_seconds"] = float(d["duration_seconds"]) if d["duration_seconds"] is not None else None
        result.append(d)
    return result


def job_summary(conn: Connection) -> list[dict[str, Any]]:
    """每個 job_name 的最後一次執行 + 近 7 天失敗次數 + 總執行次數，依 job_name 升冪。"""
    sql = text("""
        WITH last AS (
            SELECT DISTINCT ON (job_name)
                   job_name, status, target_date, target_key, rows, started_at, finished_at
            FROM etl_job_log
            ORDER BY job_name, started_at DESC, job_id DESC
        ),
        agg AS (
            SELECT job_name,
                   COUNT(*) AS total_runs,
                   COUNT(*) FILTER (
                       WHERE status = 'failed' AND started_at >= now() - INTERVAL '7 days'
                   ) AS failed_last_7_days
            FROM etl_job_log
            GROUP BY job_name
        )
        SELECT last.job_name,
               last.status       AS last_status,
               last.target_date  AS last_target_date,
               last.target_key   AS last_target_key,
               last.rows         AS last_rows,
               last.started_at   AS last_started_at,
               last.finished_at  AS last_finished_at,
               agg.total_runs,
               agg.failed_last_7_days
        FROM last JOIN agg USING (job_name)
        ORDER BY last.job_name
    """)
    rows = conn.execute(sql).fetchall()
    return [dict(row._mapping) for row in rows]
