"""create stock and trading_calendar

Revision ID: 0001
Revises:
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from twstock_db.timescale import ensure_timescaledb

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """建立 stock 和 trading_calendar 表。"""
    conn = op.get_bind()
    ensure_timescaledb(conn)

    op.create_table(
        "stock",
        sa.Column("stock_id", sa.VARCHAR(10), nullable=False),
        sa.Column("name", sa.VARCHAR(64), nullable=False),
        sa.Column("market", sa.VARCHAR(8), nullable=False),
        sa.Column("industry", sa.VARCHAR(64), nullable=True),
        sa.Column("listed_date", sa.Date(), nullable=True),
        sa.Column("is_etf", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("isin_code", sa.VARCHAR(12), nullable=True),
        sa.Column("cfi_code", sa.VARCHAR(6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("stock_id"),
        sa.CheckConstraint("market IN ('TWSE', 'TPEx', 'ESB')", name="ck_stock_market"),
    )
    op.create_index("ix_stock_market", "stock", ["market"])

    op.create_table(
        "trading_calendar",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("note", sa.VARCHAR(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("trade_date"),
    )


def downgrade() -> None:
    """移除 trading_calendar 和 stock 表。"""
    op.drop_table("trading_calendar")
    op.drop_index("ix_stock_market")
    op.drop_table("stock")
