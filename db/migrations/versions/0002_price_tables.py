"""create price tables and etl_job_log

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from twstock_db.timescale import create_hypertable_if_available

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """建立 daily_price、index_daily、adj_factor 和 etl_job_log 表。"""
    op.create_table(
        "daily_price",
        sa.Column("stock_id", sa.VARCHAR(10), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(12, 4), nullable=True),
        sa.Column("high", sa.Numeric(12, 4), nullable=True),
        sa.Column("low", sa.Numeric(12, 4), nullable=True),
        sa.Column("close", sa.Numeric(12, 4), nullable=True),
        sa.Column("change", sa.Numeric(12, 4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("turnover", sa.Numeric(20, 0), nullable=False, server_default=sa.text("0")),
        sa.Column("transactions", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.VARCHAR(8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("stock_id", "trade_date"),
        sa.CheckConstraint("source IN ('TWSE', 'TPEx')", name="ck_daily_price_source"),
    )
    op.create_index("ix_daily_price_trade_date", "daily_price", ["trade_date"])

    op.create_table(
        "index_daily",
        sa.Column("index_id", sa.VARCHAR(16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(14, 2), nullable=True),
        sa.Column("high", sa.Numeric(14, 2), nullable=True),
        sa.Column("low", sa.Numeric(14, 2), nullable=True),
        sa.Column("close", sa.Numeric(14, 2), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("index_id", "trade_date"),
    )
    op.create_index("ix_index_daily_trade_date", "index_daily", ["trade_date"])

    op.create_table(
        "adj_factor",
        sa.Column("stock_id", sa.VARCHAR(10), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("factor", sa.Numeric(12, 8), nullable=False),
        sa.Column("prev_close", sa.Numeric(12, 4), nullable=True),
        sa.Column("reference_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("cash_dividend", sa.Numeric(12, 6), nullable=True),
        sa.Column("stock_dividend", sa.Numeric(12, 6), nullable=True),
        sa.Column("kind", sa.VARCHAR(8), nullable=True),
        sa.Column("source", sa.VARCHAR(8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("stock_id", "ex_date"),
        sa.CheckConstraint("factor > 0", name="ck_adj_factor_positive"),
    )
    op.create_index("ix_adj_factor_ex_date", "adj_factor", ["ex_date"])

    op.create_table(
        "etl_job_log",
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("job_name", sa.VARCHAR(64), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("target_key", sa.VARCHAR(64), nullable=True),
        sa.Column("status", sa.VARCHAR(16), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
        sa.CheckConstraint("status IN ('running','success','failed','skipped')", name="ck_etl_job_log_status"),
    )
    op.create_index("ix_etl_job_log_name_started", "etl_job_log", ["job_name", sa.desc("started_at")])
    op.create_index("ix_etl_job_log_lookup", "etl_job_log", ["job_name", "target_date", "target_key", "status"])

    # 設定 sequence 為 BIGSERIAL (需要在建立表後)
    op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS etl_job_log_job_id_seq"))
    op.execute(sa.text("ALTER TABLE etl_job_log ALTER COLUMN job_id SET DEFAULT nextval('etl_job_log_job_id_seq')"))
    op.execute(sa.text("ALTER SEQUENCE etl_job_log_job_id_seq OWNED BY etl_job_log.job_id"))

    # 轉換為 hypertable（如果 TimescaleDB 可用）
    conn = op.get_bind()
    create_hypertable_if_available(conn, "daily_price", "trade_date", "1 month")
    create_hypertable_if_available(conn, "index_daily", "trade_date", "1 year")


def downgrade() -> None:
    """移除 etl_job_log、adj_factor、index_daily 和 daily_price 表。"""
    op.drop_table("etl_job_log")
    op.drop_table("adj_factor")
    op.drop_table("index_daily")
    op.drop_table("daily_price")
