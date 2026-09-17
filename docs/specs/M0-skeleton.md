# M0 骨架（skeleton）規格

- 里程碑：M0 骨架（見 `docs/plan.md`「開發里程碑」）
- 作者：Architect（claude-opus-5）｜ 日期：2026-09-18
- 相關決策：`docs/decisions.md`（D-001 ～ D-014）

## 0. 目標與完成標準

M0 交付一個「能跑起來、能搜尋到全部個股」的骨架：

1. PostgreSQL（+TimescaleDB，若有）schema 由 Alembic 管理，含 `stock`、`trading_calendar` 兩張表。
2. ETL：個股清單 parser（TWSE 上市、TPEx 上櫃，皆為 ISIN 一覽表格式）、交易日曆 parser、寫入 DB 的 loader、CLI、APScheduler 排程。
3. API：FastAPI `GET /api/stocks?q=`、`GET /api/health`。
4. Web：React + Vite 搜尋頁雛形。
5. Docker Compose：db、migrate、api、etl、web 五個 service。

**里程碑完成標準（本環境版本）**：`scripts/m0_verify.sh` 最後一行輸出 `M0 VERIFY PASSED`，
代表「臨時 PostgreSQL → Alembic migration → 用 fixture 載入上市+上櫃個股 → 啟動 API → fixture 內每一檔都能用代號與名稱搜尋到」。
真實資料來源連線與 `docker compose up` 留待使用者本機執行（見 §8）。

## 1. 共用規則（每個任務都適用）

### 1.1 環境事實

| 項目 | 值 |
| --- | --- |
| Repo 根目錄 | `/home/claude/TwStock`（以下簡稱「根目錄」） |
| Python | 本機 `python3` = 3.11；Docker 映像用 3.12。**程式必須相容 3.11**（不要用 `type X = ...` 語法、不要用 3.12 才有的 API） |
| Node | 22（npm 10） |
| PostgreSQL | 16，執行檔在 `/usr/lib/postgresql/16/bin`，**沒有 TimescaleDB** |
| 網路 | pypi / npm 可用；TWSE、TPEx、TDCC、MOPS、FinMind **連不到** |
| Docker | 可用但無法 pull 映像；只能 `docker compose ... config` 驗證語法，**不要** `up` / `build` |

### 1.2 慣例

- Bash 工具每次呼叫 cwd 會重置：**所有指令都用 `cd /home/claude/TwStock && ...` 開頭**，或用絕對路徑。
- Python 虛擬環境：根目錄 `.venv/`（已在 `.gitignore`）。一律用 `.venv/bin/python -m pytest`、`.venv/bin/alembic` 執行，不要用系統 pip 裝套件。
- 文件、註解、log 訊息、錯誤訊息用繁體中文；識別字（變數、函式、欄位、檔名）用英文。
- 每個 Python 函式都要有型別註記；公開函式要有一行繁中 docstring。
- 用 `logging.getLogger(__name__)`，不要在函式庫程式裡 `print`（只有 `cli.py` 與 `scripts/` 可以 print）。
- SQL 一律參數化（SQLAlchemy Core 或 `text()` + bind 參數），**禁止**用 f-string / `%` 把使用者輸入拼進 SQL。
- 機密一律從環境變數讀，不寫死在程式或測試（測試用的 `twstock/twstock` 臨時帳密只存在於 `scripts/pg_temp.sh` 產生的本機臨時 DB，允許）。
- 版本一律**精確鎖定**（`==`），照本文件表格，不要自行升級。
- 測試檔名在整個 repo 內要唯一（例如 `test_api_stocks.py`，不要到處都叫 `test_models.py`）。
- 測試目錄**不要**放 `__init__.py`（pytest 使用 importlib 模式）。
- 完成後依 `.claude/agents/coder.md` 格式回報，並把本文件底部狀態表中該任務改為 `IN_REVIEW`（這是 Coder 唯一可以改本文件的地方）。

### 1.3 鎖定版本

Python（`pyproject.toml` 的 `dependencies` 照抄）：

| 套件 | 版本 | 用於 |
| --- | --- | --- |
| sqlalchemy | 2.0.43 | db / api / etl |
| alembic | 1.16.5 | db |
| psycopg[binary] | 3.2.10 | db |
| fastapi | 0.115.14 | api |
| pydantic | 2.11.9 | api |
| uvicorn[standard] | 0.35.0 | api |
| httpx | 0.28.1 | etl（api 測試的 TestClient 也需要） |
| beautifulsoup4 | 4.13.5 | etl |
| apscheduler | 3.11.0 | etl（**3.x**，不要用 4.x 的 API） |
| tzdata | 2025.2 | etl（slim 映像沒有時區資料） |
| pytest | 8.4.2 | 開發（只寫在 `requirements-dev.txt`） |

前端（`web/package.json` 照抄，見 T0-5）：react 19.1.1、react-dom 19.1.1、react-router-dom 7.9.1、vite 7.1.5、@vitejs/plugin-react 5.0.2、typescript 5.9.2、vitest 3.2.4、jsdom 26.1.0、@testing-library/react 16.3.0、@testing-library/jest-dom 6.8.0、@testing-library/user-event 14.6.1、@types/react 19.1.13、@types/react-dom 19.1.9。
（Architect 已在本環境驗證這組版本可安裝，vitest / tsc / vite build 皆可跑通。）

Docker 映像：`timescale/timescaledb:2.21.3-pg16`、`python:3.12-slim-bookworm`、`node:22-alpine`、`nginx:1.27-alpine`。

### 1.4 最終目錄結構（M0 結束時）

```
TwStock/
├── .dockerignore                      # T0-6
├── .env.example                       # T0-1 加 DATABASE_URL
├── conftest.py                        # T0-1 共用 pytest fixture（DB）
├── pytest.ini                         # T0-1
├── requirements-dev.txt               # T0-1 建立，T0-2/T0-4 追加
├── db/
│   ├── pyproject.toml                 # 套件 twstock-db
│   ├── alembic.ini
│   ├── migrations/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_stock_trading_calendar.py
│   ├── twstock_db/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── engine.py
│   │   ├── tables.py
│   │   ├── timescale.py
│   │   └── testing.py
│   └── tests/
│       ├── test_db_migrations.py
│       └── test_db_timescale.py
├── etl/
│   ├── pyproject.toml                 # 套件 twstock-etl
│   ├── Dockerfile                     # T0-6
│   ├── twstock_etl/
│   │   ├── __init__.py
│   │   ├── errors.py
│   │   ├── models.py
│   │   ├── dates.py
│   │   ├── http.py
│   │   ├── sources/{__init__.py, isin.py, twse_holiday.py}
│   │   ├── loaders/{__init__.py, stock.py, calendar.py}
│   │   ├── jobs.py
│   │   ├── scheduler.py
│   │   └── cli.py
│   └── tests/
│       ├── fixtures/{README.md, isin_twse_strmode2.html, isin_tpex_strmode4.html, twse_holiday_schedule_2026.json}
│       ├── test_etl_dates.py
│       ├── test_etl_http.py
│       ├── test_etl_isin.py
│       ├── test_etl_twse_holiday.py
│       ├── test_etl_loaders.py
│       ├── test_etl_cli.py
│       └── test_etl_scheduler.py
├── api/
│   ├── pyproject.toml                 # 套件 twstock-api
│   ├── Dockerfile                     # T0-6
│   ├── twstock_api/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── deps.py
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   └── routers/{__init__.py, stocks.py, health.py}
│   └── tests/
│       ├── test_api_repository.py
│       ├── test_api_stocks.py
│       └── test_api_health.py
├── web/                               # T0-5（Dockerfile、nginx.conf 在 T0-6）
├── deploy/docker-compose.yml          # T0-6
└── scripts/
    ├── pg_temp.sh                     # T0-1
    ├── verify_search_all.py           # T0-6
    └── m0_verify.sh                   # T0-6
```

### 1.5 任務順序

```
T0-1 db 套件 + migration ─► T0-2 ETL parser ─► T0-3 ETL loader/CLI/排程 ─► T0-4 API 搜尋 ─► T0-5 Web 搜尋頁 ─► T0-6 Docker + 整合驗收
```

一次只做一個任務；前一個任務 Reviewer `APPROVE` 後才開始下一個。

---

## T0-1　Python 工作區、db 套件、Alembic migration、臨時 PostgreSQL

### 目標

建立共用的 `twstock-db` 套件（連線設定、SQLAlchemy Core 表定義、TimescaleDB 偵測工具）、Alembic 第一支 migration（`stock`、`trading_calendar`），以及本機測試用的臨時 PostgreSQL 腳本與共用 pytest fixture。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `scripts/pg_temp.sh` | 新增（可執行，`chmod +x`） |
| `pytest.ini` | 新增 |
| `conftest.py`（根目錄） | 新增 |
| `requirements-dev.txt` | 新增 |
| `.env.example` | 修改：末尾加一行 `DATABASE_URL=postgresql+psycopg://twstock:change_me@localhost:5432/twstock` |
| `db/pyproject.toml` | 新增 |
| `db/alembic.ini` | 新增 |
| `db/migrations/env.py`、`db/migrations/script.py.mako` | 新增 |
| `db/migrations/versions/0001_stock_trading_calendar.py` | 新增 |
| `db/migrations/.gitkeep` | 刪除 |
| `db/twstock_db/__init__.py`、`config.py`、`engine.py`、`tables.py`、`timescale.py`、`testing.py` | 新增 |
| `db/tests/test_db_migrations.py`、`db/tests/test_db_timescale.py` | 新增 |

### 1. `scripts/pg_temp.sh`

用法：`scripts/pg_temp.sh start|stop|reset`。

- `start`：若 `$PGDATA/PG_VERSION` 不存在就 `initdb`；若叢集沒在跑就 `pg_ctl start`；確保角色 `twstock`（密碼 `twstock`，LOGIN）與資料庫 `twstock_test`（owner `twstock`）存在；**stdout 只輸出一行連線字串** `postgresql+psycopg://twstock:twstock@127.0.0.1:<PORT>/twstock_test`。重複執行 `start` 不可報錯（冪等）。
- `stop`：`pg_ctl stop -m fast`，叢集沒在跑也不報錯，輸出 `stopped`。
- `reset`：`stop` → `rm -rf $PGDATA` → `start`。
- 環境變數：`TWSTOCK_PGDATA`（預設 `/tmp/twstock-pg`）、`TWSTOCK_PGPORT`（預設 `54329`）。
- 以 root 執行時，所有 `initdb` / `pg_ctl` / `psql` 用 `runuser -u postgres --` 執行（postgres 不能以 root 跑），並先 `chown postgres:postgres $PGDATA`。
- `initdb` 參數：`-U postgres --auth=trust -E UTF8 --locale=C.UTF-8`；`pg_ctl` 參數：`-o "-p $PORT -k /tmp -c listen_addresses=127.0.0.1" -l "$PGDATA/server.log" -w`。

參考實作（Architect 已驗證可用，可直接採用）：

```bash
#!/usr/bin/env bash
# 本機測試用臨時 PostgreSQL 16 叢集（無 TimescaleDB）。用法：scripts/pg_temp.sh start|stop|reset
set -euo pipefail
PGBIN=/usr/lib/postgresql/16/bin
PGDATA=${TWSTOCK_PGDATA:-/tmp/twstock-pg}
PORT=${TWSTOCK_PGPORT:-54329}
as_pg() { if [ "$(id -u)" = "0" ]; then runuser -u postgres -- "$@"; else "$@"; fi; }
psql_pg() { as_pg $PGBIN/psql -h 127.0.0.1 -p "$PORT" -U postgres -v ON_ERROR_STOP=1 "$@"; }
case "${1:-}" in
start)
  if [ ! -f "$PGDATA/PG_VERSION" ]; then
    mkdir -p "$PGDATA"
    if [ "$(id -u)" = "0" ]; then chown postgres:postgres "$PGDATA"; fi
    as_pg $PGBIN/initdb -D "$PGDATA" -U postgres --auth=trust -E UTF8 --locale=C.UTF-8 >/dev/null
  fi
  as_pg $PGBIN/pg_ctl -D "$PGDATA" status >/dev/null 2>&1 || \
    as_pg $PGBIN/pg_ctl -D "$PGDATA" -o "-p $PORT -k /tmp -c listen_addresses=127.0.0.1" -l "$PGDATA/server.log" -w start >/dev/null
  psql_pg -tAc "SELECT 1 FROM pg_roles WHERE rolname='twstock'" | grep -q 1 || \
    psql_pg -c "CREATE ROLE twstock LOGIN PASSWORD 'twstock'" >/dev/null
  psql_pg -tAc "SELECT 1 FROM pg_database WHERE datname='twstock_test'" | grep -q 1 || \
    psql_pg -c "CREATE DATABASE twstock_test OWNER twstock" >/dev/null
  echo "postgresql+psycopg://twstock:twstock@127.0.0.1:$PORT/twstock_test"
  ;;
stop)
  as_pg $PGBIN/pg_ctl -D "$PGDATA" -m fast -w stop >/dev/null 2>&1 || true
  echo "stopped"
  ;;
reset)
  "$0" stop >/dev/null
  rm -rf "$PGDATA"
  "$0" start
  ;;
*)
  echo "用法：$0 start|stop|reset" >&2
  exit 2
  ;;
esac
```

### 2. `pytest.ini`（根目錄）

```ini
[pytest]
addopts = -q --import-mode=importlib
testpaths = db/tests etl/tests api/tests
```

### 3. `requirements-dev.txt`（T0-1 版本）

```
-e ./db
pytest==8.4.2
```

（T0-2 會在 `-e ./db` 下一行加 `-e ./etl`；T0-4 再加 `-e ./api`。順序固定：db、etl、api、pytest。）

### 4. `db/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "twstock-db"
version = "0.1.0"
description = "TwStock 共用資料庫定義與 migration"
requires-python = ">=3.11"
dependencies = [
  "sqlalchemy==2.0.43",
  "alembic==1.16.5",
  "psycopg[binary]==3.2.10",
]

[tool.setuptools.packages.find]
include = ["twstock_db*"]
```

### 5. `twstock_db` 模組介面

`config.py`

```python
DATABASE_URL_ENV = "DATABASE_URL"

def get_database_url() -> str:
    """從環境變數 DATABASE_URL 讀取 SQLAlchemy 連線字串。"""
    # 未設定或空字串 → raise RuntimeError("環境變數 DATABASE_URL 未設定")
```

`engine.py`

```python
from functools import lru_cache
from sqlalchemy import Engine

@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    """建立（並快取）SQLAlchemy Engine；url 為 None 時讀 DATABASE_URL。"""
    # create_engine(url or get_database_url(), pool_pre_ping=True)
```

`tables.py`：`metadata = MetaData()`，以及與下方 DDL **完全一致**的 `stock`、`trading_calendar` 兩個 `sqlalchemy.Table`（欄位名、型別、nullable、server_default 都要一致）。只用 SQLAlchemy Core，**不要**寫 ORM class。

`timescale.py`

```python
def timescaledb_available(conn: Connection) -> bool:
    """此 PostgreSQL 是否安裝了 timescaledb 擴充套件檔（pg_available_extensions）。"""
    # SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'

def timescaledb_installed(conn: Connection) -> bool:
    """目前資料庫是否已 CREATE EXTENSION timescaledb（pg_extension）。"""
    # SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'

def ensure_timescaledb(conn: Connection) -> bool:
    """若可用則 CREATE EXTENSION IF NOT EXISTS timescaledb 並回傳 True；不可用回傳 False 並記 INFO log。"""

def create_hypertable_if_available(
    conn: Connection, table: str, time_column: str, chunk_interval: str = "1 month"
) -> bool:
    """若已安裝 timescaledb，將 table 轉為 hypertable 並回傳 True；否則不做事回傳 False。"""
    # 1. table、time_column 必須符合 ^[a-z_][a-z0-9_]*$，否則 raise ValueError（在檢查擴充之前就驗證）
    # 2. 未安裝 → logger.info("未安裝 TimescaleDB，%s 維持一般資料表", table)，return False
    # 3. 已安裝 → 執行（參數化）：
    #    SELECT create_hypertable(CAST(:table AS regclass), :time_column,
    #           chunk_time_interval => CAST(:interval AS interval),
    #           if_not_exists => TRUE, migrate_data => TRUE)
    #    return True
```

M0 的兩張表都是維度表，**不轉** hypertable；`create_hypertable_if_available` 是給 M1 以後的 migration 用，M0 只需實作與測試。

`testing.py`（只給測試用）

```python
from pathlib import Path
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

def alembic_config(database_url: str) -> "alembic.config.Config":
    """回傳指向 db/alembic.ini、並設定好 sqlalchemy.url 的 Alembic Config。"""
    # cfg = Config(str(ALEMBIC_INI)); cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

def reset_database(database_url: str) -> None:
    """把測試資料庫降到 base 再升到 head（清空所有表與結構）。"""
    # command.downgrade(cfg, "base"); command.upgrade(cfg, "head")
```

### 6. Alembic 設定

`db/alembic.ini`：

```ini
[alembic]
script_location = %(here)s/migrations
file_template = %%(rev)s_%%(slug)s
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

`db/migrations/env.py` 要點（照寫）：

```python
from logging.config import fileConfig
from alembic import context
from sqlalchemy import create_engine, pool
from twstock_db.config import get_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = None  # migration 一律手寫，不使用 autogenerate

def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_database_url()

def run_migrations_offline() -> None:
    context.configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`script.py.mako`：用 Alembic 預設 generic 範本內容即可（`alembic init` 產生的那份）。

### 7. Migration `0001_stock_trading_calendar.py`

- `revision = "0001"`、`down_revision = None`、docstring 第一行 `create stock and trading_calendar`。
- `upgrade()` 第一步呼叫 `ensure_timescaledb(op.get_bind())`，接著用 `op.create_table` / `op.create_index` 建出下列結構（等價於此 DDL）：

```sql
CREATE TABLE stock (
    stock_id     VARCHAR(10)  PRIMARY KEY,                  -- 例：2330、0050、00679B
    name         VARCHAR(64)  NOT NULL,                     -- 簡稱，例：台積電
    market       VARCHAR(8)   NOT NULL,                     -- TWSE=上市、TPEx=上櫃、ESB=興櫃（M0 不載入 ESB）
    industry     VARCHAR(64),                               -- 產業別中文名稱；ETF 為 NULL
    listed_date  DATE,
    is_etf       BOOLEAN      NOT NULL DEFAULT false,
    is_active    BOOLEAN      NOT NULL DEFAULT true,
    isin_code    VARCHAR(12),
    cfi_code     VARCHAR(6),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_stock_market CHECK (market IN ('TWSE', 'TPEx', 'ESB'))
);
CREATE INDEX ix_stock_market ON stock (market);

CREATE TABLE trading_calendar (
    trade_date   DATE         PRIMARY KEY,                  -- 台北時間日期
    is_open      BOOLEAN      NOT NULL,
    note         VARCHAR(64),                               -- 休市原因，例：農曆除夕及春節、週末
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
```

- `downgrade()`：`op.drop_table("trading_calendar")`、`op.drop_index("ix_stock_market")`、`op.drop_table("stock")`。**不要** DROP EXTENSION。

### 8. 根目錄 `conftest.py`（所有套件共用）

```python
TEST_DB_ENV = "TWSTOCK_TEST_DATABASE_URL"

@pytest.fixture(scope="session")
def database_url() -> str:
    # 讀 os.environ[TEST_DB_ENV]；未設定 → pytest.skip("未設定 TWSTOCK_TEST_DATABASE_URL，略過 DB 測試")

@pytest.fixture(scope="session")
def db_engine(database_url: str) -> Iterator[Engine]:
    # twstock_db.testing.reset_database(database_url)；engine = create_engine(database_url)；yield；engine.dispose()

@pytest.fixture()
def clean_db(db_engine: Engine) -> Engine:
    # 以 engine.begin() 執行 TRUNCATE <metadata.sorted_tables 所有表名，逗號分隔>；回傳 db_engine
```

### 9. 測試

`db/tests/test_db_migrations.py`（使用 `db_engine`）：

1. `test_tables_exist`：`sqlalchemy.inspect(engine).get_table_names()` 包含 `stock`、`trading_calendar`、`alembic_version`。
2. `test_tables_py_matches_database`：對 `tables.metadata` 每張表，DB 欄位名稱集合 == `Table.columns` 名稱集合。
3. `test_stock_market_check_constraint`：插入 `market='XXX'` 會丟 `sqlalchemy.exc.IntegrityError`。
4. `test_stock_defaults`：只給 `stock_id, name, market` 插入後，`is_etf=False`、`is_active=True`、`created_at` 非 NULL。
5. `test_downgrade_then_upgrade`：呼叫 `reset_database` 後表仍存在（驗證 downgrade/upgrade 可逆）。

`db/tests/test_db_timescale.py`：

1. `test_invalid_identifier_raises`：`create_hypertable_if_available(conn, "stock; DROP", "trade_date")` → `ValueError`（這個測試用 `db_engine` 連線即可）。
2. `test_available_matches_catalog`：`timescaledb_available(conn)` 等於直接查 `pg_available_extensions` 的結果。
3. `test_hypertable_noop_without_timescale`：若 `timescaledb_installed(conn)` 為 True 就 `pytest.skip`；否則 `create_hypertable_if_available(conn, "trading_calendar", "trade_date")` 回傳 `False`。
4. `test_get_database_url_missing`：用 `monkeypatch.delenv("DATABASE_URL", raising=False)` 後呼叫 `get_database_url()` → `RuntimeError`。

### 驗收指令

```bash
cd /home/claude/TwStock && python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt && echo INSTALL_OK
# 預期：最後一行 INSTALL_OK

cd /home/claude/TwStock && scripts/pg_temp.sh reset && scripts/pg_temp.sh start
# 預期：兩行皆為 postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test

cd /home/claude/TwStock && DATABASE_URL=postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test .venv/bin/alembic -c db/alembic.ini upgrade head
# 預期 stderr 含：Running upgrade  -> 0001, create stock and trading_calendar
#            以及：TimescaleDB 不可用的 INFO log（訊息內容自訂，需為繁中）

cd /home/claude/TwStock && psql postgresql://twstock:twstock@127.0.0.1:54329/twstock_test -c '\d stock' -c '\d trading_calendar'
# 預期：欄位、型別、預設值、ck_stock_market、ix_stock_market 與 §7 DDL 一致

cd /home/claude/TwStock && DATABASE_URL=postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test .venv/bin/alembic -c db/alembic.ini downgrade base && DATABASE_URL=postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test .venv/bin/alembic -c db/alembic.ini upgrade head && echo REVERSIBLE_OK
# 預期：最後一行 REVERSIBLE_OK

cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test .venv/bin/python -m pytest db/tests -rs
# 預期：9 passed、0 skipped（本環境無 TimescaleDB，test_hypertable_noop_without_timescale 應為 passed 而非 skipped）

cd /home/claude/TwStock && .venv/bin/python -m pytest db/tests -rs
# 預期：不設 TWSTOCK_TEST_DATABASE_URL 時，DB 測試顯示 skipped 而非 error；test_get_database_url_missing 仍 passed
```

### 不要做的事

- 不要建立 `daily_price` 或任何 M1 之後的表；不要建 `etl_job_log`（M1 才做）。
- 不要把任何表轉成 hypertable；不要安裝 `pg_trgm`。
- 不要用 Alembic autogenerate；不要寫 ORM model class。
- 不要改 `docs/`（狀態表除外）、不要動 `etl/`、`api/`、`web/`、`deploy/`。

---

## T0-2　ETL 來源 parser：個股清單（TWSE/TPEx ISIN）與 TWSE 休市日

### 目標

建立 `twstock-etl` 套件的純函式層：日期解析、HTTP 重試、ISIN 一覽表 parser（上市 strMode=2、上櫃 strMode=4）、TWSE 休市日 parser 與交易日曆產生。**這個任務不碰資料庫。**

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `etl/pyproject.toml` | 新增 |
| `etl/twstock_etl/__init__.py`（空）、`errors.py`、`models.py`、`dates.py`、`http.py` | 新增 |
| `etl/twstock_etl/sources/__init__.py`（空）、`sources/isin.py`、`sources/twse_holiday.py` | 新增 |
| `etl/tests/fixtures/README.md`、`isin_twse_strmode2.html`、`isin_tpex_strmode4.html`、`twse_holiday_schedule_2026.json` | 新增（內容見下） |
| `etl/tests/test_etl_dates.py`、`test_etl_http.py`、`test_etl_isin.py`、`test_etl_twse_holiday.py` | 新增 |
| `etl/.gitkeep` | 刪除 |
| `requirements-dev.txt` | 在 `-e ./db` 下一行加 `-e ./etl` |

### 1. `etl/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "twstock-etl"
version = "0.1.0"
description = "TwStock ETL worker"
requires-python = ">=3.11"
dependencies = [
  "twstock-db",
  "httpx==0.28.1",
  "beautifulsoup4==4.13.5",
  "apscheduler==3.11.0",
  "tzdata==2025.2",
]

[tool.setuptools.packages.find]
include = ["twstock_etl*"]
```

### 2. `errors.py`、`models.py`

```python
# errors.py
class SourceFormatError(Exception):
    """來源資料格式不符預期（欄位缺漏、解析結果為空、筆數異常）。"""

# models.py
from dataclasses import dataclass
from datetime import date
from typing import Literal

Market = Literal["TWSE", "TPEx", "ESB"]

@dataclass(frozen=True)
class StockRecord:
    stock_id: str            # 例 "2330"
    name: str                # 例 "台積電"
    market: Market
    industry: str | None     # 產業別中文；空字串要轉成 None
    listed_date: date | None
    is_etf: bool
    isin_code: str | None
    cfi_code: str | None

@dataclass(frozen=True)
class Holiday:
    holiday_date: date
    name: str                # 例 "農曆除夕及春節"
    description: str         # 可為空字串
    is_trading_day: bool     # 「開始交易日」「最後交易日」這類條目為 True

@dataclass(frozen=True)
class CalendarDay:
    trade_date: date
    is_open: bool
    note: str | None
```

### 3. `dates.py`

```python
def parse_tw_date(value: str) -> date:
    """解析台灣官方資料常見日期格式（民國或西元）。"""
```

先 `value.strip()`，依序判斷（都不符 → `raise ValueError(f"無法解析日期：{value!r}")`）：

| 輸入 | 規則 | 結果 |
| --- | --- | --- |
| `"2026-01-05"`、`"2026/01/05"` | `^\d{4}[-/]\d{2}[-/]\d{2}$` 西元 | 2026-01-05 |
| `"20260105"` | 8 位數字，西元 | 2026-01-05 |
| `"1150105"` | 7 位數字，前 3 位民國年 +1911 | 2026-01-05 |
| `"990105"` | 6 位數字，前 2 位民國年 +1911 | 2010-01-05 |
| `"115/01/05"`、`"99/1/5"` | `^\d{2,3}/\d{1,2}/\d{1,2}$` 民國 | 2026-01-05、2010-01-05 |
| `"2026-02-30"` | 格式對但日期不存在 | `ValueError` |
| `""`、`"--"`、`"abc"` | — | `ValueError` |

### 4. `http.py`

```python
DEFAULT_HEADERS = {"User-Agent": "TwStock/0.1 (personal use)"}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

def default_client(timeout: float = 30.0, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """建立帶預設 headers、timeout、follow_redirects=True 的 httpx.Client；transport 僅供測試注入。"""

def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    attempts: int = 3,
    backoff_seconds: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET 並在連線錯誤或可重試狀態碼時重試；最後仍失敗則拋出例外。"""
```

行為：

- 第 i 次（i 從 1 起）失敗後若還有剩餘次數，`logger.warning(...)` 然後 `sleep(backoff_seconds * i)`，再試。
- `httpx.TransportError`（含逾時）→ 可重試；最後一次仍失敗 → 原例外往外丟。
- 狀態碼在 `RETRYABLE_STATUS` → 可重試；最後一次仍失敗 → `response.raise_for_status()` 丟 `httpx.HTTPStatusError`。
- 其他 4xx（例如 402、404）→ **不重試**，立刻 `raise_for_status()`。
- 2xx → 回傳 response。

### 5. `sources/isin.py`

來源：

| market | URL |
| --- | --- |
| `TWSE` | `https://isin.twse.com.tw/isin/C_public.jsp?strMode=2` |
| `TPEx` | `https://isin.twse.com.tw/isin/C_public.jsp?strMode=4` |

```python
ISIN_URLS: dict[str, str] = {...上表...}
STOCK_SECTIONS = frozenset({"股票", "創新板股票"})
ETF_SECTIONS = frozenset({"ETF"})
_CODE_RE = re.compile(r"^[0-9A-Z]{4,6}$")

def decode_isin_bytes(raw: bytes) -> str:
    """ISIN 網頁為 MS950 編碼：先試 cp950 嚴格解碼，失敗改用 big5hkscs 並 errors='replace'。"""

def fetch_isin_html(market: str, client: httpx.Client | None = None) -> str:
    """下載指定市場的 ISIN 一覽表並回傳解碼後字串。market 只接受 TWSE / TPEx，否則 ValueError。"""
    # client 為 None 時用 default_client() 並在結束時 close；用 get_with_retry；回傳 decode_isin_bytes(resp.content)

def parse_isin_html(html: str, market: str) -> list[StockRecord]:
    """解析 ISIN 一覽表 HTML，只保留「股票」「創新板股票」「ETF」區段。"""
```

`parse_isin_html` 演算法（照做）：

1. `market` 不是 `TWSE`/`TPEx` → `ValueError`。
2. `soup = BeautifulSoup(html, "html.parser")`，`current_section: str | None = None`，`seen: set[str]`。
3. 對 `soup.find_all("tr")` 的每個 `tr`：`tds = tr.find_all("td", recursive=False)`；`cells = [td.get_text(strip=True) for td in tds]`。
   - `len(tds) == 1`：這是區段列，`current_section = cells[0]`（例 `"股票"`、`"ETF"`、`"上市認購(售)權證"`；頁首標題表也是 1 格，會被當成不認得的區段，沒關係）。
   - `len(tds) >= 7`：
     - `cells[0].startswith("有價證券代號及名稱")` → 表頭，跳過。
     - `current_section` 不在 `STOCK_SECTIONS | ETF_SECTIONS` → 跳過。
     - 拆代號與名稱：`cells[0]` 以全形空白 `"　"` 分割一次；若沒有全形空白，改用 `split(None, 1)`；分不出兩段 → `logger.warning` 並跳過。代號、名稱各自 `strip()`。
     - 代號不符 `_CODE_RE` → `logger.warning` 跳過。代號已在 `seen` → 跳過（保留第一筆）。
     - `listed_date`：`cells[2]` 空字串 → `None`；否則 `parse_tw_date`，失敗 → `logger.warning` 並設 `None`（**不**跳過該列）。
     - `industry = cells[4] or None`、`isin_code = cells[1] or None`、`cfi_code = cells[5] or None`。
     - `is_etf = current_section in ETF_SECTIONS`。
   - 其他格數 → 跳過。
4. 結果為空 list → `raise SourceFormatError(f"ISIN 一覽表解析結果為空（market={market}），可能是格式變動")`。
5. 回傳順序 = 網頁出現順序。

注意：**市場別以參數 `market` 為準**，不要用第 4 欄「市場別」判斷（創新板該欄是「上市臺灣創新板」之類的字）。

### 6. `sources/twse_holiday.py`

來源：`https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule`（TWSE OpenAPI「有價證券集中交易市場開（休）市日期」，回傳**當年度** JSON 陣列）。

單筆格式（fixture 依此撰寫）：

```json
{"Name": "農曆除夕及春節", "Date": "1150216", "Weekday": "一", "Description": "依規定放假。"}
```

```python
HOLIDAY_URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
TRADING_DAY_KEYWORDS = ("開始交易", "最後交易")

def fetch_holiday_schedule(client: httpx.Client | None = None) -> list[dict[str, str]]:
    """下載 TWSE 休市日 JSON；回傳不是 list → SourceFormatError。"""

def parse_holiday_schedule(payload: list[dict[str, str]]) -> list[Holiday]:
    """把 OpenAPI JSON 轉成 Holiday 清單。"""

def build_calendar(year: int, holidays: Sequence[Holiday]) -> list[CalendarDay]:
    """產生該年 1/1～12/31 每一天的 CalendarDay。"""
```

`parse_holiday_schedule` 規則：

- 每筆必須有 `Name`、`Date` 鍵，缺任一 → `SourceFormatError`（訊息含該筆內容）。`Description` 缺 → 視為 `""`。
- `holiday_date = parse_tw_date(Date)`；`ValueError` → 轉成 `SourceFormatError`。
- `is_trading_day = any(k in Name or k in Description for k in TRADING_DAY_KEYWORDS)`。
- 空陣列 → 回傳空 list（不報錯；是否足夠由 `build_calendar` 的呼叫端判斷）。

`build_calendar` 規則：

- `holidays` 中 `holiday_date.year != year` 的忽略。
- 過濾後若沒有任何一筆 → `raise SourceFormatError(f"休市日資料不含 {year} 年")`（避免誤把所有平日當開市）。
- 對每一天 `d`：
  1. 該日有任一 `is_trading_day=False` 的 Holiday → `is_open=False`，`note=` 第一筆此類 Holiday 的 `name`（截到 64 字）。
  2. 否則若 `d.weekday() >= 5` → `is_open=False`，`note="週末"`。
  3. 否則 → `is_open=True`，`note=None`（包含「開始交易日」「最後交易日」條目）。
- 回傳依日期排序、長度 365 或 366。

### 7. Fixture

`etl/tests/fixtures/README.md`：列表說明每個 fixture 的來源 URL、撰寫日期 2026-09-18、「手寫樣本，依官方公開格式撰寫，資料值僅供測試，不保證與現況一致」、原始網頁編碼（ISIN 為 MS950，fixture 以 UTF-8 儲存；編碼路徑由 `test_decode_isin_bytes_cp950` 另外覆蓋）。

`etl/tests/fixtures/isin_twse_strmode2.html`（**照抄**，代號與名稱之間是全形空白 U+3000）：

```html
<!-- 手寫樣本：依 https://isin.twse.com.tw/isin/C_public.jsp?strMode=2 公開格式撰寫（2026-09-18）。資料值僅供測試。原始網頁為 MS950，本檔為 UTF-8。 -->
<html><head><meta http-equiv="Content-Type" content="text/html; charset=MS950">
<title></title></head>
<body>
<table align=center><tr><td><h2><strong><font class='h1'>本國上市證券國際證券辨識號碼一覽表</font></strong></h2></td></tr></table>
<table align=center><tr><td align=center><font color='#FF0000'>最近更新日期:2026/09/17</font></td></tr></table>
<table width='100%' class='h4' align=center cellSpacing=3 cellPadding=2 border=0>
<tr align=center><td bgcolor=#D5FFD5>有價證券代號及名稱 </td><td bgcolor=#D5FFD5>國際證券辨識號碼(ISIN Code)</td><td bgcolor=#D5FFD5>上市日</td><td bgcolor=#D5FFD5>市場別</td><td bgcolor=#D5FFD5>產業別</td><td bgcolor=#D5FFD5>CFICode</td><td bgcolor=#D5FFD5>備註</td></tr>
<tr><td bgcolor=#FAFAD2 colspan=7 ><B> 股票<B> </td></tr>
<tr><td bgcolor=#FAFAD2>1101　台泥</td><td bgcolor=#FAFAD2>TW0001101004</td><td bgcolor=#FAFAD2>1962/02/09</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2>水泥工業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>2317　鴻海</td><td bgcolor=#FAFAD2>TW0002317005</td><td bgcolor=#FAFAD2>1991/06/18</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2>其他電子業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>2330　台積電</td><td bgcolor=#FAFAD2>TW0002330008</td><td bgcolor=#FAFAD2>1994/09/05</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2>半導體業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>2834　臺企銀</td><td bgcolor=#FAFAD2>TW0002834009</td><td bgcolor=#FAFAD2>1998/01/13</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2>金融保險業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>2881　富邦金</td><td bgcolor=#FAFAD2>TW0002881000</td><td bgcolor=#FAFAD2>2001/12/19</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2>金融保險業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>6415　矽力*-KY</td><td bgcolor=#FAFAD2>KYG8190F1028</td><td bgcolor=#FAFAD2>2013/12/12</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2>半導體業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2 colspan=7 ><B> 上市認購(售)權證<B> </td></tr>
<tr><td bgcolor=#FAFAD2>030001　台積電元大5A購01</td><td bgcolor=#FAFAD2>TW18Z0300016</td><td bgcolor=#FAFAD2>2026/05/20</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2></td><td bgcolor=#FAFAD2>RWSCCE</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2 colspan=7 ><B> 特別股<B> </td></tr>
<tr><td bgcolor=#FAFAD2>2881A　富邦特</td><td bgcolor=#FAFAD2>TW0002881A08</td><td bgcolor=#FAFAD2>2016/12/12</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2>金融保險業</td><td bgcolor=#FAFAD2>EPNRAR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2 colspan=7 ><B> ETF<B> </td></tr>
<tr><td bgcolor=#FAFAD2>0050　元大台灣50</td><td bgcolor=#FAFAD2>TW0000050004</td><td bgcolor=#FAFAD2>2003/06/30</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2></td><td bgcolor=#FAFAD2>CEOGEU</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>0056　元大高股息</td><td bgcolor=#FAFAD2>TW0000056001</td><td bgcolor=#FAFAD2>2007/12/26</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2></td><td bgcolor=#FAFAD2>CEOGEU</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>00878　國泰永續高股息</td><td bgcolor=#FAFAD2>TW00000878Y6</td><td bgcolor=#FAFAD2>2020/07/20</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2></td><td bgcolor=#FAFAD2>CEOGEU</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2 colspan=7 ><B> 臺灣存託憑證(TDR)<B> </td></tr>
<tr><td bgcolor=#FAFAD2>9105　泰金寶-DR</td><td bgcolor=#FAFAD2>TW0009105009</td><td bgcolor=#FAFAD2>1997/10/09</td><td bgcolor=#FAFAD2>上市</td><td bgcolor=#FAFAD2>存託憑證</td><td bgcolor=#FAFAD2>EDSDDR</td><td bgcolor=#FAFAD2></td></tr>
</table>
</body></html>
```

→ 預期解析 9 筆（股票 6、ETF 3），依序：`1101, 2317, 2330, 2834, 2881, 6415, 0050, 0056, 00878`。

`etl/tests/fixtures/isin_tpex_strmode4.html`（**照抄**，結構同上）：

```html
<!-- 手寫樣本：依 https://isin.twse.com.tw/isin/C_public.jsp?strMode=4 公開格式撰寫（2026-09-18）。資料值僅供測試。原始網頁為 MS950，本檔為 UTF-8。 -->
<html><head><meta http-equiv="Content-Type" content="text/html; charset=MS950">
<title></title></head>
<body>
<table align=center><tr><td><h2><strong><font class='h1'>本國上櫃證券國際證券辨識號碼一覽表</font></strong></h2></td></tr></table>
<table align=center><tr><td align=center><font color='#FF0000'>最近更新日期:2026/09/17</font></td></tr></table>
<table width='100%' class='h4' align=center cellSpacing=3 cellPadding=2 border=0>
<tr align=center><td bgcolor=#D5FFD5>有價證券代號及名稱 </td><td bgcolor=#D5FFD5>國際證券辨識號碼(ISIN Code)</td><td bgcolor=#D5FFD5>上市日</td><td bgcolor=#D5FFD5>市場別</td><td bgcolor=#D5FFD5>產業別</td><td bgcolor=#D5FFD5>CFICode</td><td bgcolor=#D5FFD5>備註</td></tr>
<tr><td bgcolor=#FAFAD2 colspan=7 ><B> 股票<B> </td></tr>
<tr><td bgcolor=#FAFAD2>3105　穩懋</td><td bgcolor=#FAFAD2>TW0003105003</td><td bgcolor=#FAFAD2>2010/03/12</td><td bgcolor=#FAFAD2>上櫃</td><td bgcolor=#FAFAD2>半導體業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>4966　譜瑞-KY</td><td bgcolor=#FAFAD2>KYG7250A1016</td><td bgcolor=#FAFAD2>2011/03/18</td><td bgcolor=#FAFAD2>上櫃</td><td bgcolor=#FAFAD2>半導體業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>5347　世界</td><td bgcolor=#FAFAD2>TW0005347009</td><td bgcolor=#FAFAD2>1998/03/30</td><td bgcolor=#FAFAD2>上櫃</td><td bgcolor=#FAFAD2>半導體業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>5483　中美晶</td><td bgcolor=#FAFAD2>TW0005483002</td><td bgcolor=#FAFAD2>2001/08/03</td><td bgcolor=#FAFAD2>上櫃</td><td bgcolor=#FAFAD2>半導體業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>6488　環球晶</td><td bgcolor=#FAFAD2>TW0006488000</td><td bgcolor=#FAFAD2>2015/09/25</td><td bgcolor=#FAFAD2>上櫃</td><td bgcolor=#FAFAD2>半導體業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>8069　元太</td><td bgcolor=#FAFAD2>TW0008069006</td><td bgcolor=#FAFAD2>2003/12/08</td><td bgcolor=#FAFAD2>上櫃</td><td bgcolor=#FAFAD2>光電業</td><td bgcolor=#FAFAD2>ESVUFR</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2 colspan=7 ><B> 上櫃認購(售)權證<B> </td></tr>
<tr><td bgcolor=#FAFAD2>70001P　穩懋群益5A售01</td><td bgcolor=#FAFAD2>TW27Z70001P5</td><td bgcolor=#FAFAD2>2026/06/02</td><td bgcolor=#FAFAD2>上櫃</td><td bgcolor=#FAFAD2></td><td bgcolor=#FAFAD2>RWSPPE</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2 colspan=7 ><B> ETF<B> </td></tr>
<tr><td bgcolor=#FAFAD2>006201　元大富櫃50</td><td bgcolor=#FAFAD2>TW0000620107</td><td bgcolor=#FAFAD2>2011/01/27</td><td bgcolor=#FAFAD2>上櫃</td><td bgcolor=#FAFAD2></td><td bgcolor=#FAFAD2>CEOGEU</td><td bgcolor=#FAFAD2></td></tr>
<tr><td bgcolor=#FAFAD2>00679B　元大美債20年</td><td bgcolor=#FAFAD2>TW00000679B0</td><td bgcolor=#FAFAD2>2017/01/17</td><td bgcolor=#FAFAD2>上櫃</td><td bgcolor=#FAFAD2></td><td bgcolor=#FAFAD2>CEOJLU</td><td bgcolor=#FAFAD2></td></tr>
</table>
</body></html>
```

→ 預期解析 8 筆（股票 6、ETF 2），依序：`3105, 4966, 5347, 5483, 6488, 8069, 006201, 00679B`。

`etl/tests/fixtures/twse_holiday_schedule_2026.json`（**照抄**；JSON 不能放註解，來源寫在 README.md）：

```json
[
  {"Name": "中華民國開國紀念日", "Date": "1150101", "Weekday": "四", "Description": "依規定放假1日。"},
  {"Name": "國曆新年開始交易日", "Date": "1150102", "Weekday": "五", "Description": "國曆新年開始交易。"},
  {"Name": "農曆春節前最後交易日", "Date": "1150211", "Weekday": "三", "Description": "農曆春節前最後交易日。"},
  {"Name": "市場無交易，僅辦理結算交割作業", "Date": "1150212", "Weekday": "四", "Description": ""},
  {"Name": "市場無交易，僅辦理結算交割作業", "Date": "1150213", "Weekday": "五", "Description": ""},
  {"Name": "農曆除夕及春節", "Date": "1150216", "Weekday": "一", "Description": "依規定放假。"},
  {"Name": "農曆除夕及春節", "Date": "1150217", "Weekday": "二", "Description": "依規定放假。"},
  {"Name": "農曆除夕及春節", "Date": "1150218", "Weekday": "三", "Description": "依規定放假。"},
  {"Name": "農曆除夕及春節", "Date": "1150219", "Weekday": "四", "Description": "依規定放假。"},
  {"Name": "農曆除夕及春節", "Date": "1150220", "Weekday": "五", "Description": "調整放假。"},
  {"Name": "農曆春節後開始交易日", "Date": "1150223", "Weekday": "一", "Description": "農曆春節後開始交易。"},
  {"Name": "和平紀念日", "Date": "1150227", "Weekday": "五", "Description": "2月28日（星期六）逢例假日，於2月27日補假1日。"},
  {"Name": "和平紀念日", "Date": "1150228", "Weekday": "六", "Description": "逢例假日。"},
  {"Name": "兒童節及民族掃墓節", "Date": "1150403", "Weekday": "五", "Description": "補假。"},
  {"Name": "兒童節及民族掃墓節", "Date": "1150406", "Weekday": "一", "Description": "補假。"}
]
```

→ 2026 年共 365 天：平日 261 天，其中 11 天休市 → **開市 250 天、休市 115 天**。

### 8. 測試（全部不需要 DB）

`test_etl_dates.py`：用 `pytest.mark.parametrize` 覆蓋 §3 表格每一列（成功與 ValueError 都要）。

`test_etl_http.py`：用 `httpx.MockTransport` 建 `httpx.Client(transport=...)`，`sleep` 傳入記錄呼叫的假函式：

1. 第 1 次 503、第 2 次 200 → 回傳 200；`sleep` 被呼叫 1 次，參數 `5.0`。
2. 三次都 503 → `httpx.HTTPStatusError`；`sleep` 呼叫參數依序 `[5.0, 10.0]`。
3. 404 → 立即 `HTTPStatusError`，transport 只被呼叫 1 次，`sleep` 未被呼叫。
4. 402 → 同 404（不重試）。
5. 前兩次 transport 丟 `httpx.ConnectError("boom")`、第 3 次 200 → 回傳 200。
6. `test_default_client_user_agent`：`default_client(transport=MockTransport(handler))` 發出的 request，`request.headers["User-Agent"] == "TwStock/0.1 (personal use)"`。

`test_etl_isin.py`：

1. `test_parse_twse_fixture`：讀 fixture（`Path(__file__).parent / "fixtures" / ...`，`encoding="utf-8"`）→ 9 筆、代號順序同 §7、全部 `market == "TWSE"`。
2. `test_parse_twse_record_fields`：2330 → `name="台積電"`、`industry="半導體業"`、`listed_date=date(1994,9,5)`、`is_etf=False`、`isin_code="TW0002330008"`、`cfi_code="ESVUFR"`。
3. `test_parse_twse_etf`：0050 → `is_etf=True`、`industry is None`。
4. `test_parse_skips_non_stock_sections`：結果不含 `030001`、`2881A`、`9105`。
5. `test_parse_name_with_symbols`：6415 名稱 `"矽力*-KY"`；2834 名稱 `"臺企銀"`（**不要**在 parser 內把臺改成台）。
6. `test_parse_tpex_fixture`：8 筆、順序同 §7、全部 `market == "TPEx"`；`00679B` 為 ETF。
7. `test_parse_empty_raises`：`parse_isin_html("<html></html>", "TWSE")` → `SourceFormatError`。
8. `test_parse_invalid_market`：`market="XYZ"` → `ValueError`。
9. `test_parse_bad_rows_skipped`：自組 HTML 字串（一個「股票」區段 + 三列：正常 `2330　台積電`；無分隔 `2330台積電`；代號 `23-0　壞`）→ 只回 1 筆。
10. `test_parse_invalid_listed_date_keeps_row`：上市日 `2026/13/40` → 該筆 `listed_date is None` 但仍存在。
11. `test_parse_halfwidth_space_fallback`：`"2330 台積電"`（半形空白）也能解析。
12. `test_decode_isin_bytes_cp950`：`decode_isin_bytes(fixture_text.encode("cp950"))` 解析後結果與直接解析 UTF-8 相同。

`test_etl_twse_holiday.py`：

1. `test_parse_fixture`：15 筆；`1150102` 那筆 `is_trading_day=True`；`1150101` 為 False。
2. `test_parse_missing_key_raises`：`[{"Name": "x"}]` → `SourceFormatError`。
3. `test_parse_bad_date_raises`：`[{"Name": "x", "Date": "abc"}]` → `SourceFormatError`。
4. `test_build_calendar_counts`：fixture → 365 天、開市 250、休市 115。
5. `test_build_calendar_specific_days`：`2026-01-01` 休市 note `"中華民國開國紀念日"`；`2026-01-02` 開市 note None；`2026-01-03` 休市 note `"週末"`；`2026-02-12` 休市；`2026-02-11` 開市；`2026-02-28` 休市 note `"和平紀念日"`（假日優先於週末）。
6. `test_build_calendar_wrong_year_raises`：fixture + `year=2025` → `SourceFormatError`。
7. `test_build_calendar_leap_year`：`year=2028` 搭配一筆 `Holiday(date(2028,1,1), ...)` → 366 天。

### 驗收指令

```bash
cd /home/claude/TwStock && .venv/bin/pip install -q -r requirements-dev.txt && echo INSTALL_OK
# 預期：INSTALL_OK

cd /home/claude/TwStock && .venv/bin/python -m pytest etl/tests -rs
# 預期：全部 passed、0 failed、0 skipped（本任務沒有 DB 測試）

cd /home/claude/TwStock && .venv/bin/python -c "
from pathlib import Path
from twstock_etl.sources.isin import parse_isin_html
for f, m in [('isin_twse_strmode2.html','TWSE'),('isin_tpex_strmode4.html','TPEx')]:
    rs = parse_isin_html(Path('etl/tests/fixtures/'+f).read_text(encoding='utf-8'), m)
    print(m, len(rs), sum(r.is_etf for r in rs))
"
# 預期輸出：
# TWSE 9 3
# TPEx 8 2
```

### 不要做的事

- 不要連線到任何外部網站（測試一律用 fixture 或 MockTransport）。
- 不要寫資料庫相關程式（loader、CLI 屬 T0-3）。
- 不要解析 TDR、權證、特別股、ETN、興櫃（strMode=5）。
- 不要用 pandas / lxml（只用 BeautifulSoup + `html.parser`）。
- 不要在 parser 做「臺→台」正規化（搜尋時才做，屬 T0-4）。

---

## T0-3　ETL loader、job、CLI、排程

### 目標

把 T0-2 的解析結果冪等寫入 DB，提供 CLI（可從本機檔案載入，供本環境與 fixture 驗證），以及 APScheduler 每日排程。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `etl/twstock_etl/loaders/__init__.py`（空）、`loaders/stock.py`、`loaders/calendar.py` | 新增 |
| `etl/twstock_etl/jobs.py`、`scheduler.py`、`cli.py` | 新增 |
| `etl/tests/test_etl_loaders.py`、`test_etl_cli.py`、`test_etl_scheduler.py` | 新增 |

### 1. `loaders/stock.py`

```python
BATCH_SIZE = 1000

def upsert_stocks(conn: Connection, records: Sequence[StockRecord]) -> int:
    """以 INSERT ... ON CONFLICT (stock_id) DO UPDATE 寫入個股，回傳處理筆數。"""

def deactivate_missing(conn: Connection, market: str, keep_ids: Collection[str]) -> int:
    """把該 market 中 is_active=true 但不在 keep_ids 內的個股設為 is_active=false，回傳異動筆數。"""
```

- `upsert_stocks`：使用 `sqlalchemy.dialects.postgresql.insert(tables.stock)`；每 `BATCH_SIZE` 筆一批；`on_conflict_do_update(index_elements=["stock_id"], set_={...})` 更新 `name, market, industry, listed_date, is_etf, isin_code, cfi_code`，並設 `is_active=True`、`updated_at=func.now()`。**不更新** `created_at`。`records` 為空 → 回傳 0 且不發 SQL。
- `deactivate_missing`：`UPDATE stock SET is_active=false, updated_at=now() WHERE market=:market AND is_active AND stock_id NOT IN (...)`，用 Core：`tables.stock.c.stock_id.not_in(list(keep_ids))`。`keep_ids` 為空 → `raise ValueError("keep_ids 不可為空")`（防止整個市場被停用）。
- 兩個函式都**不**自己 commit；交易由呼叫端（`jobs.py`）控制。

### 2. `loaders/calendar.py`

```python
def upsert_calendar(conn: Connection, days: Sequence[CalendarDay]) -> int:
    """以 ON CONFLICT (trade_date) DO UPDATE 寫入交易日曆，回傳筆數。"""
```

更新 `is_open, note`，`updated_at=func.now()`。空 → 回傳 0。

### 3. `jobs.py`

```python
MIN_RECORDS_FOR_DEACTIVATE = 500

@dataclass(frozen=True)
class StockLoadResult:
    market: str
    records: int
    deactivated: int

@dataclass(frozen=True)
class CalendarLoadResult:
    year: int
    days: int
    open_days: int
    closed_days: int

def refresh_stock_list(
    engine: Engine,
    market: str,
    *,
    html: str | None = None,
    deactivate: bool = False,
    client: httpx.Client | None = None,
) -> StockLoadResult:
    """取得（或使用傳入的）ISIN HTML，解析後在單一交易內寫入 stock。"""

def refresh_trading_calendar(
    engine: Engine,
    year: int,
    *,
    payload: list[dict[str, str]] | None = None,
    client: httpx.Client | None = None,
) -> CalendarLoadResult:
    """取得（或使用傳入的）休市日 JSON，產生該年日曆並寫入 trading_calendar。"""
```

- `refresh_stock_list`：`html is None` → `fetch_isin_html(market, client)`；`records = parse_isin_html(html, market)`；若 `deactivate and len(records) < MIN_RECORDS_FOR_DEACTIVATE` → `raise SourceFormatError(f"{market} 個股僅 {n} 筆，少於 {MIN_RECORDS_FOR_DEACTIVATE}，拒絕停用缺漏個股")`（在寫 DB **之前**檢查）；`with engine.begin() as conn:` 內依序 `upsert_stocks`、（若 `deactivate`）`deactivate_missing(conn, market, {r.stock_id for r in records})`；結束 `logger.info`。
- `refresh_trading_calendar`：`payload is None` → `fetch_holiday_schedule(client)`；`days = build_calendar(year, parse_holiday_schedule(payload))`；`with engine.begin()` 內 `upsert_calendar`。

### 4. `cli.py`

用 `argparse`（不要用 click/typer）。入口：`python -m twstock_etl.cli <command> ...`；檔案底部 `if __name__ == "__main__": raise SystemExit(main())`。

```python
def main(argv: list[str] | None = None) -> int:
    """CLI 進入點，回傳 exit code。"""
```

| 子指令 | 參數 | 成功時 stdout（一行，格式固定） |
| --- | --- | --- |
| `load-stocks` | `--market {TWSE,TPEx}`（必填）、`--file PATH`（選填，本機 ISIN HTML，UTF-8 讀取；給檔案時不連網）、`--deactivate-missing`（旗標） | `loaded market=TWSE records=9 deactivated=0` |
| `load-calendar` | `--year INT`（選填，預設台北時間今年）、`--file PATH`（選填，本機 JSON） | `loaded year=2026 days=365 open=250 closed=115` |
| `scheduler` | 無 | 無（阻塞執行排程） |

- `main` 一開始 `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")`（log 走 stderr）。
- Engine：`twstock_db.engine.get_engine()`（讀 `DATABASE_URL`）。
- 錯誤處理：`SourceFormatError`、`httpx.HTTPError`、`RuntimeError`（DATABASE_URL 未設定）、`FileNotFoundError`、`sqlalchemy.exc.SQLAlchemyError` → stderr 印 `error: <訊息>`，回傳 `1`。argparse 參數錯誤維持 argparse 預設（exit 2）。
- 台北時間：`zoneinfo.ZoneInfo("Asia/Taipei")`。

### 5. `scheduler.py`

```python
TAIPEI = ZoneInfo("Asia/Taipei")

def run_stock_list_job(engine: Engine) -> None:
    """依序刷新 TWSE、TPEx 個股清單（deactivate=True）；單一市場失敗只記 log 不中斷另一個。"""

def run_calendar_job(engine: Engine) -> None:
    """刷新台北時間今年的交易日曆；失敗只記 log（logger.exception）。"""

def build_scheduler(engine: Engine) -> BlockingScheduler:
    """建立（未啟動的）排程器並註冊 M0 的兩個 job。"""
```

`build_scheduler`：`BlockingScheduler(timezone=TAIPEI)`，註冊：

| job id | 函式 | trigger | 其他參數 |
| --- | --- | --- | --- |
| `refresh_stock_list` | `run_stock_list_job` | `CronTrigger(hour=8, minute=0, timezone=TAIPEI)` | `args=[engine]`、`coalesce=True`、`max_instances=1`、`misfire_grace_time=3600`、`next_run_time=datetime.now(TAIPEI)`（啟動時先跑一次） |
| `refresh_trading_calendar` | `run_calendar_job` | `CronTrigger(hour=7, minute=30, timezone=TAIPEI)` | 同上 |

CLI `scheduler` 子指令：`build_scheduler(get_engine()).start()`，捕捉 `KeyboardInterrupt` 後回傳 0。

### 6. 測試

`test_etl_loaders.py`（使用根目錄 `clean_db` fixture）：

1. `test_upsert_stocks_insert`：TWSE fixture 解析結果寫入 → 回傳 9；DB 內 9 列。
2. `test_upsert_stocks_idempotent`：同一批寫兩次 → DB 仍 9 列；`created_at` 不變。
3. `test_upsert_stocks_updates_fields`：先寫入 2330 名稱「台積電」，再以 `dataclasses.replace(rec, name="台積")` 寫入 → DB 名稱為「台積」、`updated_at` ≥ 原值。
4. `test_upsert_reactivates`：手動把 2330 `is_active` 設 false，再 upsert → true。
5. `test_deactivate_missing`：寫入 TWSE 9 筆，`deactivate_missing(conn, "TWSE", {"2330"})` → 回傳 8；TPEx 資料（先寫入 8 筆）不受影響。
6. `test_deactivate_missing_empty_raises`：`keep_ids=set()` → `ValueError`。
7. `test_upsert_calendar_idempotent`：fixture 日曆寫兩次 → 365 列；`SELECT count(*) WHERE is_open` = 250。
8. `test_refresh_stock_list_with_html`：`refresh_stock_list(engine, "TPEx", html=fixture)` → `StockLoadResult("TPEx", 8, 0)`。
9. `test_refresh_stock_list_deactivate_guard`：`deactivate=True` + fixture（9 筆 < 500）→ `SourceFormatError`，且 DB 內 0 列（證明在寫入前就擋下）。

`test_etl_cli.py`（使用 `clean_db`；用 `monkeypatch.setenv("DATABASE_URL", database_url)` 並在測試前後呼叫 `twstock_db.engine.get_engine.cache_clear()`；用 `capsys` 取輸出）：

1. `main(["load-stocks", "--market", "TWSE", "--file", <twse fixture>])` → 回傳 0；stdout 為 `loaded market=TWSE records=9 deactivated=0\n`。
2. 同上 TPEx → `loaded market=TPEx records=8 deactivated=0`。
3. `main(["load-calendar", "--year", "2026", "--file", <json fixture>])` → `loaded year=2026 days=365 open=250 closed=115`。
4. `load-calendar --year 2025 --file <json fixture>` → 回傳 1；stderr 以 `error: ` 開頭。
5. `load-stocks --market TWSE --file /nonexistent.html` → 回傳 1。
6. `load-stocks --market TWSE --file <fixture> --deactivate-missing` → 回傳 1（筆數保護）。
7. 未設定 `DATABASE_URL`（`monkeypatch.delenv`）→ 回傳 1，stderr 含 `DATABASE_URL`。此測試**不需要** DB fixture。

`test_etl_scheduler.py`（不需要 DB，engine 傳 `create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")`，不會真的連線）：

1. `{j.id for j in build_scheduler(engine).get_jobs()} == {"refresh_stock_list", "refresh_trading_calendar"}`。
2. 兩個 job 的 `trigger` 都是 `CronTrigger` 且 `str(trigger.timezone) == "Asia/Taipei"`。
3. `run_stock_list_job`：用 `monkeypatch.setattr("twstock_etl.scheduler.refresh_stock_list", fake)`，fake 對 TWSE 丟 `SourceFormatError`、對 TPEx 正常回傳 → 函式不丟例外，且 fake 被呼叫兩次（TWSE、TPEx 各一次，`deactivate=True`）。（因此 `scheduler.py` 必須用 `from twstock_etl.jobs import refresh_stock_list, refresh_trading_calendar` 匯入。）

### 驗收指令

```bash
cd /home/claude/TwStock && scripts/pg_temp.sh start
# 預期：postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test

cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test .venv/bin/python -m pytest db/tests etl/tests -rs
# 預期：全部 passed、0 skipped

cd /home/claude/TwStock && export DATABASE_URL=postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test && .venv/bin/alembic -c db/alembic.ini upgrade head 2>/dev/null; \
.venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html 2>/dev/null && \
.venv/bin/python -m twstock_etl.cli load-stocks --market TPEx --file etl/tests/fixtures/isin_tpex_strmode4.html 2>/dev/null && \
.venv/bin/python -m twstock_etl.cli load-stocks --market TPEx --file etl/tests/fixtures/isin_tpex_strmode4.html 2>/dev/null && \
.venv/bin/python -m twstock_etl.cli load-calendar --year 2026 --file etl/tests/fixtures/twse_holiday_schedule_2026.json 2>/dev/null && \
psql postgresql://twstock:twstock@127.0.0.1:54329/twstock_test -tAc "SELECT market, count(*), sum(is_etf::int) FROM stock GROUP BY market ORDER BY market"
# 預期輸出（第二次 TPEx 載入證明冪等，筆數不變）：
# loaded market=TWSE records=9 deactivated=0
# loaded market=TPEx records=8 deactivated=0
# loaded market=TPEx records=8 deactivated=0
# loaded year=2026 days=365 open=250 closed=115
# TPEx|8|2
# TWSE|9|3
```

（注意：pytest 的 `db_engine` 會 reset 測試 DB；上面第三段指令要在 pytest **之後**執行。）

### 不要做的事

- 不要建立 `etl_job_log` 表或寫 job log 到 DB（M1）。
- 不要實作其他資料集（日 K、法人…）；不要加 FinMind。
- 不要在 loader 裡 commit；不要在 CLI 以外的地方 print。
- 測試中不要實際 `scheduler.start()`，不要連外網。

---

## T0-4　API：FastAPI 個股搜尋與健康檢查

### 目標

提供 `GET /api/stocks?q=`（代號前綴 / 名稱包含、臺台互通、排序）與 `GET /api/health`。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `api/pyproject.toml` | 新增 |
| `api/twstock_api/__init__.py`（空）、`main.py`、`deps.py`、`schemas.py`、`repository.py` | 新增 |
| `api/twstock_api/routers/__init__.py`（空）、`routers/stocks.py`、`routers/health.py` | 新增 |
| `api/tests/test_api_repository.py`、`test_api_stocks.py`、`test_api_health.py` | 新增 |
| `api/.gitkeep` | 刪除 |
| `requirements-dev.txt` | 在 `-e ./etl` 下一行加 `-e ./api` |

### 1. `api/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "twstock-api"
version = "0.1.0"
description = "TwStock API"
requires-python = ">=3.11"
dependencies = [
  "twstock-db",
  "fastapi==0.115.14",
  "pydantic==2.11.9",
  "uvicorn[standard]==0.35.0",
  "httpx==0.28.1",
]

[tool.setuptools.packages.find]
include = ["twstock_api*"]
```

### 2. API 契約

#### `GET /api/stocks`

| 參數 | 型別 | 規則 |
| --- | --- | --- |
| `q` | string，必填 | 長度 1–50（FastAPI `Query(min_length=1, max_length=50)`）；`strip()` 後為空 → 422 |
| `limit` | int，選填 | 預設 20，範圍 1–100（`ge=1, le=100`） |

比對規則（`q` 先 `strip()`，再把「臺」換成「台」得到 `norm`）：

- 只回 `is_active = true` 的個股。
- 命中條件：`stock_id` 以 `norm` 開頭（不分大小寫）**或** `replace(name, '臺', '台')` 包含 `norm`（不分大小寫）。
- 排序：① `upper(stock_id) = upper(norm)` 完全相符 → ② 代號前綴 → ③ 名稱前綴 → ④ 名稱包含；同級依 `length(stock_id)`、`stock_id` 升冪。
- `%`、`_`、`!` 必須跳脫（當成一般字元），用 `ESCAPE '!'`。
- `count` = 本次回傳的 `items` 長度（不是總筆數）。

回應 200 範例（`GET /api/stocks?q=臺積`）：

```json
{
  "query": "臺積",
  "count": 1,
  "items": [
    {
      "stock_id": "2330",
      "name": "台積電",
      "market": "TWSE",
      "industry": "半導體業",
      "listed_date": "1994-09-05",
      "is_etf": false
    }
  ]
}
```

- `query` 回傳**原始 strip 後**的字串（不做臺台轉換）。
- 查無資料 → 200，`{"query": "zzz", "count": 0, "items": []}`。
- 參數錯誤 → FastAPI 預設 422 格式；`q` 全空白時 `raise HTTPException(status_code=422, detail="q 不可為空白")`。

#### `GET /api/health`

- DB 可連（`SELECT 1` 成功）→ 200 `{"status": "ok", "db": "ok"}`
- DB 失敗（任何 `SQLAlchemyError`）→ 503 `{"status": "error", "db": "unreachable"}`（用 `JSONResponse`，不要把例外訊息回給前端；例外寫 `logger.exception`）。

### 3. 模組介面

`schemas.py`

```python
class StockItem(BaseModel):
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx", "ESB"]
    industry: str | None
    listed_date: date | None
    is_etf: bool

class StockSearchResponse(BaseModel):
    query: str
    count: int
    items: list[StockItem]

class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    db: Literal["ok", "unreachable"]
```

`repository.py`

```python
LIKE_ESCAPE = "!"

def escape_like(value: str) -> str:
    """跳脫 LIKE 特殊字元：! → !!、% → !%、_ → !_（先處理 !）。"""

def normalize_query(q: str) -> str:
    """strip 並把「臺」轉成「台」。"""

def search_stocks(conn: Connection, q: str, limit: int) -> list[dict[str, Any]]:
    """依 §2 規則搜尋個股，回傳 dict 清單（鍵同 StockItem 欄位）。"""
```

`search_stocks` 使用的 SQL（照用，參數化）：

```sql
SELECT stock_id, name, market, industry, listed_date, is_etf
FROM stock
WHERE is_active
  AND (stock_id ILIKE :id_prefix ESCAPE '!'
       OR replace(name, '臺', '台') ILIKE :name_contains ESCAPE '!')
ORDER BY
  CASE
    WHEN upper(stock_id) = upper(:exact) THEN 0
    WHEN stock_id ILIKE :id_prefix ESCAPE '!' THEN 1
    WHEN replace(name, '臺', '台') ILIKE :name_prefix ESCAPE '!' THEN 2
    ELSE 3
  END,
  length(stock_id),
  stock_id
LIMIT :limit
```

參數：`norm = normalize_query(q)`、`e = escape_like(norm)`；`exact=norm`、`id_prefix=e + "%"`、`name_prefix=e + "%"`、`name_contains="%" + e + "%"`、`limit=limit`。

`deps.py`

```python
def get_db_engine() -> Engine:
    """FastAPI dependency：回傳 twstock_db.engine.get_engine()。"""
```

`routers/stocks.py`：`router = APIRouter(prefix="/api/stocks", tags=["stocks"])`；`@router.get("", response_model=StockSearchResponse)`；**同步** `def`（不要 async），`engine: Engine = Depends(get_db_engine)`，`with engine.connect() as conn:` 呼叫 `search_stocks`。

`routers/health.py`：`router = APIRouter(prefix="/api", tags=["health"])`；`@router.get("/health", response_model=HealthResponse)`。

`main.py`

```python
def create_app() -> FastAPI:
    """建立 FastAPI app 並掛上 routers。"""
    # FastAPI(title="TwStock API", version="0.1.0")；include health、stocks router；不加 CORS（前端走同源 proxy）

app = create_app()
```

### 4. 測試

`test_api_repository.py`（不需要 DB）：

- `escape_like`：`"50%" → "50!%"`、`"a_b" → "a!_b"`、`"x!y" → "x!!y"`、`"!%" → "!!!%"`。
- `normalize_query`：`" 臺積 " → "台積"`。

`test_api_stocks.py`（使用 `clean_db`；每個測試前以 SQL 插入下列資料；`client = TestClient(create_app())` 並設 `app.dependency_overrides[get_db_engine] = lambda: clean_db`）：

| stock_id | name | market | industry | listed_date | is_etf | is_active |
| --- | --- | --- | --- | --- | --- | --- |
| 2330 | 台積電 | TWSE | 半導體業 | 1994-09-05 | false | true |
| 2317 | 鴻海 | TWSE | 其他電子業 | 1991-06-18 | false | true |
| 2834 | 臺企銀 | TWSE | 金融保險業 | 1998-01-13 | false | true |
| 0050 | 元大台灣50 | TWSE | NULL | 2003-06-30 | true | true |
| 00679B | 元大美債20年 | TPEx | NULL | 2017-01-17 | true | true |
| 5347 | 世界 | TPEx | 半導體業 | 1998-03-30 | false | true |
| 9999 | 已下市測試 | TWSE | NULL | NULL | false | **false** |

測試案例（每個都斷言 status 與 `[i["stock_id"] for i in items]`）：

| # | 請求 | 預期 status | 預期 stock_id 順序 / 其他 |
| --- | --- | --- | --- |
| 1 | `?q=2330` | 200 | `["2330"]`，且 items[0] 完整等於 §2 範例物件 |
| 2 | `?q=23` | 200 | `["2317", "2330"]` |
| 3 | `?q=台積` | 200 | `["2330"]` |
| 4 | `?q=臺積` | 200 | `["2330"]`，`query == "臺積"` |
| 5 | `?q=台企` | 200 | `["2834"]`（DB 內是「臺企銀」） |
| 6 | `?q=00679b` | 200 | `["00679B"]`（大小寫不敏感） |
| 7 | `?q=元大` | 200 | `["0050", "00679B"]`（皆名稱前綴，依代號長度） |
| 8 | `?q=50` | 200 | `["0050"]`（名稱「元大台灣50」包含 50；代號無 50 開頭） |
| 9 | `?q=已下市` | 200 | `[]`，`count == 0` |
| 10 | `?q=%25` （即 `%`） | 200 | `[]` |
| 11 | `?q=2&limit=1` | 200 | 長度 1 |
| 12 | 無 `q` | 422 | — |
| 13 | `?q=%20%20` | 422 | — |
| 14 | `?q=2330&limit=0`、`limit=101` | 422 | — |
| 15 | `?q=` + 51 個 `a` | 422 | — |

`test_api_health.py`：

1. override 成 `clean_db` → 200 `{"status": "ok", "db": "ok"}`。
2. override 成 `create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")` → 503 `{"status": "error", "db": "unreachable"}`。

### 驗收指令

```bash
cd /home/claude/TwStock && .venv/bin/pip install -q -r requirements-dev.txt && scripts/pg_temp.sh start && echo READY
# 預期：最後一行 READY

cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test .venv/bin/python -m pytest -rs
# 預期：db、etl、api 全部 passed、0 skipped

cd /home/claude/TwStock && export DATABASE_URL=postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test && \
.venv/bin/alembic -c db/alembic.ini upgrade head 2>/dev/null && \
.venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html 2>/dev/null && \
(.venv/bin/uvicorn twstock_api.main:app --host 127.0.0.1 --port 18000 >/tmp/twstock-api.log 2>&1 &) && sleep 3 && \
curl -s 'http://127.0.0.1:18000/api/health' && echo && \
curl -s -G 'http://127.0.0.1:18000/api/stocks' --data-urlencode 'q=臺積' && echo && \
pkill -f 'uvicorn twstock_api.main:app --host 127.0.0.1 --port 18000'
# 預期：
# loaded market=TWSE records=9 deactivated=0
# {"status":"ok","db":"ok"}
# {"query":"臺積","count":1,"items":[{"stock_id":"2330","name":"台積電","market":"TWSE","industry":"半導體業","listed_date":"1994-09-05","is_etf":false}]}
```

### 不要做的事

- 不要做 `/api/stocks/{id}` 或任何價格端點（M1）。
- 不要加 CORS、認證、Redis 快取、pg_trgm、拼音搜尋。
- 不要用 async SQLAlchemy / asyncpg；不要寫 ORM。
- 不要在 SQL 裡用字串拼接帶入 `q`。

---

## T0-5　Web：React + Vite 搜尋頁雛形

### 目標

建立前端專案：首頁為搜尋頁（輸入代號或名稱、即時列出結果、`/` 快捷鍵聚焦），點結果進入 `/stock/:id` 占位頁。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `web/package.json` | 新增（內容照抄下方） |
| `web/package-lock.json` | 由 `npm install` 產生並 commit |
| `web/index.html`、`web/vite.config.ts`、`web/tsconfig.json` | 新增 |
| `web/src/main.tsx`、`App.tsx`、`api.ts`、`styles.css`、`setupTests.ts` | 新增 |
| `web/src/pages/SearchPage.tsx`、`web/src/pages/StockPage.tsx` | 新增 |
| `web/src/api.test.ts`、`web/src/pages/SearchPage.test.tsx` | 新增 |
| `web/.gitkeep` | 刪除 |

### 1. 設定檔（照抄）

`web/package.json`

```json
{
  "name": "twstock-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -p tsconfig.json && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "19.1.1",
    "react-dom": "19.1.1",
    "react-router-dom": "7.9.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "6.8.0",
    "@testing-library/react": "16.3.0",
    "@testing-library/user-event": "14.6.1",
    "@types/react": "19.1.13",
    "@types/react-dom": "19.1.9",
    "@vitejs/plugin-react": "5.0.2",
    "jsdom": "26.1.0",
    "typescript": "5.9.2",
    "vite": "7.1.5",
    "vitest": "3.2.4"
  }
}
```

`web/vite.config.ts`

```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
  },
})
```

`web/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "types": ["vite/client", "vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vite.config.ts"]
}
```

`web/src/setupTests.ts`：一行 `import '@testing-library/jest-dom/vitest'`。

`web/index.html`：`<html lang="zh-Hant">`、`<meta charset="UTF-8">`、`<meta name="viewport" content="width=device-width, initial-scale=1.0">`、`<title>TwStock</title>`、`<div id="root"></div>`、`<script type="module" src="/src/main.tsx"></script>`。

### 2. `src/api.ts`

```ts
export type Market = 'TWSE' | 'TPEx' | 'ESB'

export interface StockItem {
  stock_id: string
  name: string
  market: Market
  industry: string | null
  listed_date: string | null   // "YYYY-MM-DD"
  is_etf: boolean
}

export interface StockSearchResponse {
  query: string
  count: number
  items: StockItem[]
}

/** 市場代碼轉中文：TWSE→上市、TPEx→上櫃、ESB→興櫃 */
export function marketLabel(market: Market): string

/** 呼叫 GET /api/stocks；非 2xx 丟 Error(`HTTP ${status}`) */
export async function searchStocks(q: string, signal?: AbortSignal): Promise<StockSearchResponse>
```

`searchStocks` 請求 URL 固定為 `` `/api/stocks?q=${encodeURIComponent(q)}&limit=20` ``，呼叫 `fetch(url, { signal })`。

### 3. 頁面行為

`App.tsx`：`BrowserRouter` 不放在 App 裡（放在 `main.tsx`），App 只放 `<Routes>`：

| path | element |
| --- | --- |
| `/` | `<SearchPage />` |
| `/stock/:stockId` | `<StockPage />` |
| `*` | `<p>找不到頁面</p>` |

App 最外層 `<header>` 顯示 `<Link to="/">TwStock</Link>`。

`main.tsx`：`createRoot(document.getElementById('root')!).render(<StrictMode><BrowserRouter><App /></BrowserRouter></StrictMode>)`，並 `import './styles.css'`。

`SearchPage.tsx`（`export default function SearchPage()`）：

| 項目 | 規格 |
| --- | --- |
| 輸入框 | `<input type="search">`，`aria-label="搜尋股票代號或名稱"`，`placeholder="輸入代號或名稱，例如 2330 或 台積"`，`autoFocus` |
| 防抖 | 輸入變動後 250ms 才呼叫 `searchStocks`；用 `useEffect` + `setTimeout`，cleanup 時 `clearTimeout` 並 `abort()` 上一個 `AbortController` |
| 空字串 | `q.trim() === ''` → 清空結果、不呼叫 API、不顯示任何提示 |
| 載入中 | 顯示 `<p role="status">搜尋中…</p>` |
| 錯誤 | 顯示 `<p role="alert">搜尋失敗：{error.message}</p>`；`AbortError`（`err.name === 'AbortError'`）要忽略 |
| 無結果 | 查詢完成且 `items.length === 0` → `<p>查無符合的股票</p>` |
| 結果清單 | `<ul aria-label="搜尋結果">`，每筆 `<li>` 內：`<Link to={`/stock/${item.stock_id}`}>{item.stock_id} {item.name}</Link>`（代號與名稱之間一個半形空白，**在同一個文字節點**：`` {`${item.stock_id} ${item.name}`} ``）、`<span>{marketLabel(item.market)}</span>`、`item.is_etf` 時 `<span>ETF</span>`、`item.industry` 非 null 時 `<span>{item.industry}</span>` |
| 快捷鍵 | `document` 上監聽 `keydown`：`event.key === '/'` 且 `document.activeElement` 不是 `INPUT`/`TEXTAREA` → `preventDefault()` 並 focus 輸入框（用 `useRef`）；unmount 時移除監聽 |

`StockPage.tsx`：`useParams()` 取 `stockId`，顯示 `<h1>股票 {stockId}</h1>` 與 `<p>個股頁（K 線、籌碼）將於 M1 實作。</p>`。

`styles.css`：簡單即可（系統字型、最大寬度 720px 置中、清單項目間距）。不要引入 CSS 框架。

### 4. 測試（vitest + Testing Library）

`src/api.test.ts`：

1. `marketLabel('TWSE') === '上市'`、`'TPEx' → '上櫃'`、`'ESB' → '興櫃'`。
2. `vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({query:'台積',count:0,items:[]}), {status:200})))`，呼叫 `searchStocks('台積')` → fetch 第一個參數為 `/api/stocks?q=%E5%8F%B0%E7%A9%8D&limit=20`。
3. fetch 回 `status: 500` → `searchStocks` reject，訊息 `HTTP 500`。
4. 每個測試後 `vi.unstubAllGlobals()`。

`src/pages/SearchPage.test.tsx`（`render(<MemoryRouter><SearchPage /></MemoryRouter>)`；用真實計時器 + `findBy*`，不要用 fake timers）：

1. 輸入 `2330`（`userEvent.type`）→ `await screen.findByText('2330 台積電')` 出現；`上市` 出現；`fetch` 被呼叫且 URL 含 `q=2330`；連結 `href` 為 `/stock/2330`。
2. API 回 `items: []` → `findByText('查無符合的股票')`。
3. fetch 回 500 → `findByRole('alert')` 文字含 `搜尋失敗`。
4. ETF 結果（`is_etf: true`、`industry: null`）→ 顯示 `ETF`。
5. 快捷鍵：先讓焦點在 `document.body`（例如 `input.blur()`），`await userEvent.keyboard('/')` → 輸入框 `toHaveFocus()`。
6. 輸入後清空（`userEvent.clear`）→ 不顯示結果清單、不顯示「查無」。

### 驗收指令

```bash
cd /home/claude/TwStock/web && npm install --no-audit --no-fund && echo NPM_OK
# 預期：最後一行 NPM_OK；產生 package-lock.json

cd /home/claude/TwStock/web && npm test
# 預期：Test Files 2 passed、Tests 至少 10 passed、0 failed

cd /home/claude/TwStock/web && npm run build
# 預期：tsc 無錯誤；最後出現 ✓ built in ...；產生 web/dist/（dist 已被 .gitignore 忽略）
```

### 不要做的事

- 不要做 K 線、圖表、Lightweight Charts、ECharts（M1）。
- 不要加 UI 框架（MUI、Tailwind、antd…）、狀態管理套件、axios。
- 不要改 `package.json` 的版本號；不要升級到 vite 8 / vitest 4+ / TypeScript 6+。
- 不要 commit `node_modules/` 或 `dist/`。

---

## T0-6　Docker Compose、Dockerfile、M0 整合驗收腳本

### 目標

寫好五個 service 的 Docker Compose 與三個 Dockerfile（本環境只驗證語法），並提供 `scripts/m0_verify.sh` 以臨時 PostgreSQL + fixture 完成里程碑驗收；更新 README 的啟動說明。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `.dockerignore`（根目錄） | 新增 |
| `api/Dockerfile`、`etl/Dockerfile`、`web/Dockerfile`、`web/nginx.conf` | 新增 |
| `deploy/docker-compose.yml` | 新增；刪除 `deploy/.gitkeep` |
| `scripts/verify_search_all.py`、`scripts/m0_verify.sh`（可執行） | 新增；刪除 `scripts/.gitkeep` |
| `README.md` | 修改：新增「快速開始」段落（見 §5）。**不要**改「目前進度」那一行（Architect 驗收後改） |

### 1. `.dockerignore`

```
.git
.venv
**/__pycache__
**/*.pyc
web/node_modules
web/dist
data
.env
docs
```

### 2. Dockerfile

建置 context 一律是 **repo 根目錄**（compose 中 `context: ..`）。

`api/Dockerfile`

```dockerfile
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Taipei
WORKDIR /app
COPY db /app/db
COPY api /app/api
RUN pip install --no-cache-dir /app/db /app/api
EXPOSE 8000
CMD ["uvicorn", "twstock_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`etl/Dockerfile`

```dockerfile
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Taipei
WORKDIR /app
COPY db /app/db
COPY etl /app/etl
RUN pip install --no-cache-dir /app/db /app/etl
CMD ["python", "-m", "twstock_etl.cli", "scheduler"]
```

`web/Dockerfile`

```dockerfile
FROM node:22-alpine AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
```

`web/nginx.conf`

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 3. `deploy/docker-compose.yml`

```yaml
# TwStock 本機部署。用法（在 repo 根目錄）：
#   cp .env.example .env   # 修改密碼
#   docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
name: twstock

x-db-url: &db_url "postgresql+psycopg://${POSTGRES_USER:-twstock}:${POSTGRES_PASSWORD:?請在 .env 設定 POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-twstock}"

services:
  db:
    image: timescale/timescaledb:2.21.3-pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-twstock}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?請在 .env 設定 POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-twstock}
      TZ: ${TZ:-Asia/Taipei}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 20

  migrate:
    build:
      context: ..
      dockerfile: etl/Dockerfile
    image: twstock-etl:local
    command: ["alembic", "-c", "/app/db/alembic.ini", "upgrade", "head"]
    environment:
      DATABASE_URL: *db_url
    depends_on:
      db:
        condition: service_healthy
    restart: "no"

  api:
    build:
      context: ..
      dockerfile: api/Dockerfile
    image: twstock-api:local
    restart: unless-stopped
    environment:
      DATABASE_URL: *db_url
      TZ: ${TZ:-Asia/Taipei}
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      migrate:
        condition: service_completed_successfully

  etl:
    build:
      context: ..
      dockerfile: etl/Dockerfile
    image: twstock-etl:local
    restart: unless-stopped
    command: ["python", "-m", "twstock_etl.cli", "scheduler"]
    environment:
      DATABASE_URL: *db_url
      FINMIND_TOKEN: ${FINMIND_TOKEN:-}
      TZ: ${TZ:-Asia/Taipei}
    depends_on:
      migrate:
        condition: service_completed_successfully

  web:
    build:
      context: ..
      dockerfile: web/Dockerfile
    image: twstock-web:local
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:80"
    depends_on:
      - api

volumes:
  pgdata: {}
```

### 4. 整合驗收腳本

`scripts/verify_search_all.py`

```python
def main(argv: list[str] | None = None) -> int:
    """對 fixture 內每一檔個股，驗證 API 能以代號與名稱搜尋到。"""
```

- 參數：`--api-base`（預設 `http://127.0.0.1:18000`）、`--twse-file`、`--tpex-file`（皆必填）。
- 以 `twstock_etl.sources.isin.parse_isin_html` 解析兩個檔案取得預期清單（TWSE 用 `"TWSE"`、TPEx 用 `"TPEx"`）。
- 用 `httpx.Client(base_url=api_base, timeout=10)`，對每筆 `r`：
  - `GET /api/stocks?q={r.stock_id}&limit=100` → `items[0].stock_id == r.stock_id` 且 `items[0].market == r.market`，否則記為失敗。
  - `GET /api/stocks?q={r.name}&limit=100` → `items` 內有 `stock_id == r.stock_id`，否則記為失敗。
- 失敗逐筆印 `FAIL <stock_id> <原因>`；全部成功印 `OK {n}/{n} stocks searchable by id and name` 並回傳 0；否則印 `FAILED {失敗數}/{n}` 回傳 1。

`scripts/m0_verify.sh`（`set -euo pipefail`，以 repo 根目錄為基準：`ROOT="$(cd "$(dirname "$0")/.." && pwd)"`）步驟：

1. 使用獨立的臨時叢集：`export TWSTOCK_PGDATA=/tmp/twstock-pg-verify TWSTOCK_PGPORT=54330`；`DATABASE_URL="$("$ROOT/scripts/pg_temp.sh" reset)"`；`export DATABASE_URL`。
2. `trap` 在 EXIT 時：kill uvicorn（若已啟動）、`"$ROOT/scripts/pg_temp.sh" stop`。
3. `echo "== migrate"`；`"$ROOT/.venv/bin/alembic" -c "$ROOT/db/alembic.ini" upgrade head`。
4. `echo "== load fixtures"`；依序執行 CLI：TWSE fixture、TPEx fixture、calendar 2026 fixture（stdout 照印）。
5. `echo "== start api"`；背景啟動 `"$ROOT/.venv/bin/uvicorn" twstock_api.main:app --host 127.0.0.1 --port 18000`（log 寫到 `/tmp/twstock-m0-api.log`），記下 PID；每 0.5 秒 `curl -sf http://127.0.0.1:18000/api/health`，最多 40 次，逾時 → 印 log 並 exit 1。
6. `echo "== verify search"`；執行 `"$ROOT/.venv/bin/python" "$ROOT/scripts/verify_search_all.py" --twse-file ... --tpex-file ...`。
7. 成功 → 最後一行 `echo "M0 VERIFY PASSED"`。

### 5. README「快速開始」段落

在 README 現有內容之後加 `## 快速開始`，包含：

- Docker（使用者本機）：`cp .env.example .env` → 改密碼 → `docker compose -f deploy/docker-compose.yml --env-file .env up -d --build` → 開 `http://localhost:8080`；首次啟動 etl 會立即抓取個股清單與交易日曆。
- 本機開發（無 Docker）：建立 `.venv`、`pip install -r requirements-dev.txt`、`scripts/pg_temp.sh start`、`alembic upgrade`、`uvicorn`、`cd web && npm run dev`（Vite proxy 到 8000）。
- 測試：`TWSTOCK_TEST_DATABASE_URL=... .venv/bin/python -m pytest`、`cd web && npm test`、`scripts/m0_verify.sh`。

### 驗收指令

```bash
cd /home/claude/TwStock && docker compose -f deploy/docker-compose.yml --env-file .env.example config --quiet && echo COMPOSE_OK
# 預期：COMPOSE_OK（無錯誤、無警告）

cd /home/claude/TwStock && docker compose -f deploy/docker-compose.yml --env-file .env.example config --services | sort
# 預期：
# api
# db
# etl
# migrate
# web

cd /home/claude/TwStock && scripts/m0_verify.sh
# 預期輸出包含（依序）：
# == migrate
# == load fixtures
# loaded market=TWSE records=9 deactivated=0
# loaded market=TPEx records=8 deactivated=0
# loaded year=2026 days=365 open=250 closed=115
# == start api
# == verify search
# OK 17/17 stocks searchable by id and name
# M0 VERIFY PASSED

cd /home/claude/TwStock && scripts/m0_verify.sh && scripts/m0_verify.sh | tail -1
# 預期：可重複執行，第二次最後一行仍為 M0 VERIFY PASSED；結束後 54330 port 上沒有 postgres、18000 port 上沒有 uvicorn

cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs && (cd web && npm test)
# 預期：既有測試全部仍通過（回歸）
```

### 不要做的事

- **不要** `docker compose up`、`docker build`、`docker pull`（本環境無法 pull，會卡住或失敗）。
- 不要寫 Helm chart、Redis、Nginx TLS。
- 不要把 `.env` 或真實密碼 commit。
- 不要修改 T0-1～T0-5 的程式邏輯；若驗收時發現前面任務的 bug，停下來回報，不要自行修。

---

## 8. 留待使用者本機驗證（本環境做不到）

| 項目 | 指令 / 方式 | 通過標準 |
| --- | --- | --- |
| Docker 全套啟動 | `docker compose -f deploy/docker-compose.yml --env-file .env up -d --build` | 五個 service 皆啟動，`migrate` exit 0 |
| TimescaleDB 路徑 | `docker compose ... exec db psql -U twstock -c '\dx'` | 看得到 `timescaledb` 擴充 |
| ISIN 真實格式 | `docker compose ... logs etl` 或本機 `python -m twstock_etl.cli load-stocks --market TWSE` | 上市約 1,000+ 筆（股票+ETF）、上櫃約 800+ 筆，無 `SourceFormatError` |
| 休市日真實格式 | `python -m twstock_etl.cli load-calendar` | 開市日約 240–250 天 |
| 全部個股可搜尋 | 開 `http://localhost:8080` 搜尋任意代號 | 找得到 |

若真實格式與 fixture 不符：以真實回應更新 fixture 與 parser，並在 `docs/decisions.md` 補記。

## 任務狀態

| 任務 | 標題 | 相依 | 狀態 | 審查報告 |
| --- | --- | --- | --- | --- |
| T0-1 | Python 工作區、db 套件、Alembic migration、臨時 PostgreSQL | — | TODO | — |
| T0-2 | ETL 來源 parser：個股清單（TWSE/TPEx ISIN）與 TWSE 休市日 | T0-1 | TODO | — |
| T0-3 | ETL loader、job、CLI、排程 | T0-2 | TODO | — |
| T0-4 | API：FastAPI 個股搜尋與健康檢查 | T0-1、T0-3（驗收用 CLI 載入） | TODO | — |
| T0-5 | Web：React + Vite 搜尋頁雛形 | T0-4（契約） | TODO | — |
| T0-6 | Docker Compose、Dockerfile、M0 整合驗收腳本 | T0-1～T0-5 | TODO | — |
