"""SQLAlchemy Core 表定義。"""
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    MetaData,
    String,
    Table,
    func,
    text,
)

metadata = MetaData()

stock = Table(
    "stock",
    metadata,
    Column("stock_id", String(10), primary_key=True),
    Column("name", String(64), nullable=False),
    Column("market", String(8), nullable=False),
    Column("industry", String(64), nullable=True),
    Column("listed_date", Date(), nullable=True),
    Column("is_etf", Boolean(), nullable=False, server_default=text("false")),
    Column("is_active", Boolean(), nullable=False, server_default=text("true")),
    Column("isin_code", String(12), nullable=True),
    Column("cfi_code", String(6), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("market IN ('TWSE', 'TPEx', 'ESB')", name="ck_stock_market"),
)

trading_calendar = Table(
    "trading_calendar",
    metadata,
    Column("trade_date", Date(), primary_key=True),
    Column("is_open", Boolean(), nullable=False),
    Column("note", String(64), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
