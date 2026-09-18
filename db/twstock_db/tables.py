"""SQLAlchemy Core 表定義。"""
from datetime import date

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
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

daily_price = Table(
    "daily_price",
    metadata,
    Column("stock_id", String(10), nullable=False, primary_key=True),
    Column("trade_date", Date(), nullable=False, primary_key=True),
    Column("open", Numeric(12, 4), nullable=True),
    Column("high", Numeric(12, 4), nullable=True),
    Column("low", Numeric(12, 4), nullable=True),
    Column("close", Numeric(12, 4), nullable=True),
    Column("change", Numeric(12, 4), nullable=True),
    Column("volume", BigInteger(), nullable=False, server_default=text("0")),
    Column("turnover", Numeric(20, 0), nullable=False, server_default=text("0")),
    Column("transactions", BigInteger(), nullable=False, server_default=text("0")),
    Column("source", String(8), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("source IN ('TWSE', 'TPEx')", name="ck_daily_price_source"),
)

index_daily = Table(
    "index_daily",
    metadata,
    Column("index_id", String(16), nullable=False, primary_key=True),
    Column("trade_date", Date(), nullable=False, primary_key=True),
    Column("open", Numeric(14, 2), nullable=True),
    Column("high", Numeric(14, 2), nullable=True),
    Column("low", Numeric(14, 2), nullable=True),
    Column("close", Numeric(14, 2), nullable=True),
    Column("volume", BigInteger(), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

adj_factor = Table(
    "adj_factor",
    metadata,
    Column("stock_id", String(10), nullable=False, primary_key=True),
    Column("ex_date", Date(), nullable=False, primary_key=True),
    Column("factor", Numeric(12, 8), nullable=False),
    Column("prev_close", Numeric(12, 4), nullable=True),
    Column("reference_price", Numeric(12, 4), nullable=True),
    Column("cash_dividend", Numeric(12, 6), nullable=True),
    Column("stock_dividend", Numeric(12, 6), nullable=True),
    Column("kind", String(8), nullable=True),
    Column("source", String(8), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("factor > 0", name="ck_adj_factor_positive"),
)

etl_job_log = Table(
    "etl_job_log",
    metadata,
    Column("job_id", BigInteger(), primary_key=True, autoincrement=True),
    Column("job_name", String(64), nullable=False),
    Column("target_date", Date(), nullable=True),
    Column("target_key", String(64), nullable=True),
    Column("status", String(16), nullable=False),
    Column("rows", Integer(), nullable=False, server_default=text("0")),
    Column("error", Text(), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    CheckConstraint("status IN ('running','success','failed','skipped')", name="ck_etl_job_log_status"),
)
