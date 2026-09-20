"""為 daily_price 加上 (stock_id, trade_date DESC) 索引。

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """為 daily_price 加上 (stock_id, trade_date DESC) 索引（U-14）。"""
    op.create_index(
        "ix_daily_price_stock_date_desc",
        "daily_price",
        ["stock_id", sa.desc("trade_date")],
    )


def downgrade() -> None:
    """移除 ix_daily_price_stock_date_desc。"""
    op.drop_index("ix_daily_price_stock_date_desc", table_name="daily_price")
