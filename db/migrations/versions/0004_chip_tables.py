"""create chip tables (institutional_daily, margin_daily, foreign_holding, shareholding_dist)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from twstock_db.timescale import create_hypertable_if_available

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """建立 institutional_daily、margin_daily、foreign_holding、shareholding_dist 表。"""
    op.create_table(
        "institutional_daily",
        sa.Column("stock_id", sa.VARCHAR(10), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("foreign_buy", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("foreign_sell", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("foreign_net", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("trust_buy", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("trust_sell", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("trust_net", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("dealer_buy", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("dealer_sell", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("dealer_net", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_net", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.VARCHAR(8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("stock_id", "trade_date"),
        sa.CheckConstraint("source IN ('TWSE', 'TPEx')", name="ck_institutional_daily_source"),
    )
    op.create_index("ix_institutional_daily_trade_date", "institutional_daily", ["trade_date"])

    op.create_table(
        "margin_daily",
        sa.Column("stock_id", sa.VARCHAR(10), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("margin_buy", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("margin_sell", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("margin_redeem", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("margin_prev_balance", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("margin_balance", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("margin_limit", sa.BigInteger(), nullable=True),
        sa.Column("short_buy", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("short_sell", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("short_redeem", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("short_prev_balance", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("short_balance", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("short_limit", sa.BigInteger(), nullable=True),
        sa.Column("offset_amount", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("sbl_sell", sa.BigInteger(), nullable=True),
        sa.Column("sbl_balance", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.VARCHAR(8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("stock_id", "trade_date"),
        sa.CheckConstraint("source IN ('TWSE', 'TPEx')", name="ck_margin_daily_source"),
    )
    op.create_index("ix_margin_daily_trade_date", "margin_daily", ["trade_date"])

    op.create_table(
        "foreign_holding",
        sa.Column("stock_id", sa.VARCHAR(10), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("issued_shares", sa.BigInteger(), nullable=True),
        sa.Column("holding_shares", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("available_shares", sa.BigInteger(), nullable=True),
        sa.Column("holding_ratio", sa.Numeric(8, 4), nullable=True),
        sa.Column("available_ratio", sa.Numeric(8, 4), nullable=True),
        sa.Column("limit_ratio", sa.Numeric(8, 4), nullable=True),
        sa.Column("source", sa.VARCHAR(8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("stock_id", "trade_date"),
        sa.CheckConstraint("source IN ('TWSE', 'TPEx')", name="ck_foreign_holding_source"),
    )
    op.create_index("ix_foreign_holding_trade_date", "foreign_holding", ["trade_date"])

    op.create_table(
        "shareholding_dist",
        sa.Column("stock_id", sa.VARCHAR(10), nullable=False),
        sa.Column("week_date", sa.Date(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("holders", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("shares", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("ratio", sa.Numeric(8, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("stock_id", "week_date", "level"),
        sa.CheckConstraint("level BETWEEN 1 AND 17", name="ck_shareholding_dist_level"),
    )
    op.create_index("ix_shareholding_dist_week", "shareholding_dist", ["week_date"])

    # 轉換為 hypertable（如果 TimescaleDB 可用）
    conn = op.get_bind()
    create_hypertable_if_available(conn, "institutional_daily", "trade_date", "1 month")
    create_hypertable_if_available(conn, "margin_daily", "trade_date", "1 month")
    create_hypertable_if_available(conn, "foreign_holding", "trade_date", "1 month")
    create_hypertable_if_available(conn, "shareholding_dist", "week_date", "1 year")


def downgrade() -> None:
    """移除 shareholding_dist、foreign_holding、margin_daily、institutional_daily 表。"""
    op.drop_table("shareholding_dist")
    op.drop_table("foreign_holding")
    op.drop_table("margin_daily")
    op.drop_table("institutional_daily")
