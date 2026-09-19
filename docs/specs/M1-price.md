# M1 價格 + K 線 規格

- 里程碑：M1 價格 + K 線（見 `docs/plan.md`「開發里程碑」）
- 作者：Architect（claude-opus-5）｜ 日期：2026-09-19
- 前一里程碑：`docs/specs/M0-skeleton.md`、驗收報告 `docs/reports/M0.md`
- 相關決策：`docs/decisions.md`（沿用 D-001 ～ D-014，新增 D-016 ～ D-026）

## 0. 目標與完成標準

M1 交付「打開個股頁就看得到正確的還原 K 線，而且每天盤後自動更新」：

1. 三張時序／事件資料表：`daily_price`（日 K）、`index_daily`（大盤指數日 K）、`adj_factor`（除權息還原係數），外加維運用的 `etl_job_log`。
2. ETL：TWSE／TPEx 日成交 parser、TAIEX 指數歷史 parser、TWSE 除權除息計算結果表 parser，以及對應的 loader、job、CLI、排程。
3. 回補腳本 `scripts/backfill.py`：含速率限制、斷點續傳、進度輸出，能在使用者 Mac 上回補 5 年。
4. API：`GET /api/stocks/{id}`、`GET /api/stocks/{id}/prices`、`GET /api/indices/{id}/prices`、`GET /api/etl/jobs`、`GET /api/etl/summary`。
5. Web：個股頁 `/stock/:id`（K 線 + MA5/20/60 + 成交量副圖 + 區間切換 + 還原價開關）、ETL 狀態頁 `/admin/etl`。

**里程碑完成標準（本環境版本）**：`scripts/m1_verify.sh` 最後一行輸出 `M1 VERIFY PASSED`。
它代表「臨時 PostgreSQL → migration → 以 fixture 離線回補指數／日 K／除權息 → 啟動 API →
`2330` 的未還原收盤價、還原收盤價、TAIEX 指數、ETL 狀態四項數值全部符合手算預期 → 再跑一次回補會全部 skip（斷點續傳）」。

真實來源連線、`docker compose up`、TimescaleDB hypertable 實跑留給使用者本機（見 §7）。

---

## 1. 共用規則（每個任務都適用）

### 1.1 環境事實（與 M0 相同，再確認一次）

| 項目 | 值 |
| --- | --- |
| Repo 根目錄 | `/home/claude/TwStock`（以下簡稱「根目錄」） |
| Python | 本機 `python3` = 3.11；Docker 映像用 3.12。**程式必須相容 3.11** |
| Node | 22（npm 10） |
| PostgreSQL | 16，執行檔在 `/usr/lib/postgresql/16/bin`，**沒有 TimescaleDB** |
| 網路 | pypi / npm 可用；TWSE、TPEx、TDCC、MOPS、FinMind **連不到**（一律用 fixture 測） |
| Docker | 可用但無法 pull / build 映像；只能 `docker compose -f deploy/docker-compose.yml --env-file .env.example config --quiet` |
| git | branch `main`，**只 commit，不要 push** |

### 1.2 慣例（沿用 M0 §1.2，重點重貼）

- Bash 每次呼叫 cwd 會重置：**所有指令都用 `cd /home/claude/TwStock && ...` 開頭**。
- 一律用 `.venv/bin/python -m pytest`、`.venv/bin/alembic`，不要用系統 pip。
- 文件、註解、log 訊息、錯誤訊息用繁體中文；識別字用英文。
- 每個 Python 函式都要有型別註記；公開函式要有一行繁中 docstring。
- `logging.getLogger(__name__)`；函式庫程式不要 `print`（只有 `cli.py`、`twstock_etl/backfill.py` 的進度輸出函式與 `scripts/` 可以 print）。
- SQL 一律參數化，**禁止** f-string／`%` 拼接使用者輸入。
- 版本一律精確鎖定（`==`），照 §1.3，不要自行升級。
- 測試檔名在整個 repo 內唯一；測試目錄不要放 `__init__.py`。
- **價格一律用 `decimal.Decimal`**，不要用 `float` 做任何價格運算（只有輸出 JSON 時才轉 `float`）。
- **不要動 M0 已通過審查的程式邏輯**，本規格明確列出的修改點除外（`jobs.py` 停用保護、`scheduler.py`、`timescale.py`、`conftest.py`、`SearchPage.tsx`、`App.tsx`、`setupTests.ts`）。
- 完成後依 `.claude/agents/coder.md` 格式回報，並把本文件底部狀態表中該任務改為 `IN_REVIEW`（這是 Coder 唯一可以改本文件的地方）。

### 1.3 版本

Python 依賴**不新增任何套件**（Decimal、json 都是標準庫）。前端新增一個：

| 套件 | 版本 | 用途 |
| --- | --- | --- |
| `lightweight-charts` | `4.2.3` | K 線圖（**v4 API**：`chart.addCandlestickSeries()` / `addLineSeries()` / `addHistogramSeries()`。**不要**用 v5 的 `chart.addSeries(CandlestickSeries, …)`） |

Architect 已於本環境實際 `npm i lightweight-charts@4.2.3` 驗證可安裝，且 `dist/typings.d.ts` 含 `addCandlestickSeries` / `addLineSeries` / `addHistogramSeries`。

### 1.4 M1 結束時新增／修改的檔案

```
TwStock/
├── conftest.py                                 # T1-1 改：TRUNCATE 加 RESTART IDENTITY CASCADE
├── db/
│   ├── twstock_db/tables.py                    # T1-1 改：加 4 張表
│   ├── twstock_db/timescale.py                 # T1-1 改：hypertable 雙簽名
│   └── migrations/versions/0002_price_tables.py# T1-1 新增
│   └── tests/test_db_hypertable.py             # T1-1 新增
├── etl/
│   ├── twstock_etl/models.py                   # T1-2 改：加 3 個 dataclass
│   ├── twstock_etl/numbers.py                  # T1-2 新增
│   ├── twstock_etl/sources/report.py           # T1-2 新增（共用 JSON 報表信封）
│   ├── twstock_etl/sources/twse_price.py       # T1-2 新增
│   ├── twstock_etl/sources/tpex_price.py       # T1-2 新增
│   ├── twstock_etl/sources/twse_index.py       # T1-2 新增
│   ├── twstock_etl/sources/twse_exright.py     # T1-2 新增
│   ├── twstock_etl/loaders/price.py            # T1-3 新增
│   ├── twstock_etl/loaders/job_log.py          # T1-3 新增
│   ├── twstock_etl/loaders/stock.py            # T1-3 改：加 count_active_stocks
│   ├── twstock_etl/jobs.py                     # T1-4 改寫
│   ├── twstock_etl/cli.py                      # T1-4 改：加 4 個子指令
│   ├── twstock_etl/scheduler.py                # T1-4 改寫
│   ├── twstock_etl/backfill.py                 # T1-5 新增（回補核心邏輯）
│   └── tests/fixtures/…                        # T1-2 新增 9 個 JSON（見 T1-2 §6）
│   └── tests/test_etl_numbers.py               # T1-2
│   └── tests/test_etl_twse_price.py            # T1-2
│   └── tests/test_etl_tpex_price.py            # T1-2
│   └── tests/test_etl_twse_index.py            # T1-2
│   └── tests/test_etl_twse_exright.py          # T1-2
│   └── tests/test_etl_price_loaders.py         # T1-3
│   └── tests/test_etl_job_log.py               # T1-3
│   └── tests/test_etl_price_jobs.py            # T1-4
│   └── tests/test_etl_backfill.py              # T1-5
├── api/
│   ├── twstock_api/adjust.py                   # T1-6 新增
│   ├── twstock_api/price_repository.py         # T1-6 新增
│   ├── twstock_api/etl_repository.py           # T1-6 新增
│   ├── twstock_api/schemas.py                  # T1-6 改：加 schema
│   ├── twstock_api/routers/prices.py           # T1-6 新增
│   ├── twstock_api/routers/indices.py          # T1-6 新增
│   ├── twstock_api/routers/etl.py              # T1-6 新增
│   ├── twstock_api/routers/stocks.py           # T1-6 改：加 GET /api/stocks/{id}
│   └── twstock_api/main.py                     # T1-6 改：掛新 router
│   └── tests/test_api_adjust.py                # T1-6
│   └── tests/test_api_prices.py                # T1-6
│   └── tests/test_api_etl.py                   # T1-6
├── web/
│   ├── package.json                            # T1-7 改：加 lightweight-charts
│   ├── src/setupTests.ts                       # T1-7 改：ResizeObserver polyfill
│   ├── src/api.ts                              # T1-7 改：加型別與 fetch 函式
│   ├── src/ma.ts                               # T1-7 新增
│   ├── src/components/CandleChart.tsx          # T1-7 新增
│   ├── src/pages/StockPage.tsx                 # T1-7 改寫
│   ├── src/pages/EtlStatusPage.tsx             # T1-7 新增
│   ├── src/pages/SearchPage.tsx                # T1-7 改：修 U-6、U-7
│   ├── src/App.tsx                             # T1-7 改：加 /admin/etl 路由
│   └── src/styles.css                          # T1-7 改：加樣式
│   └── src/ma.test.ts / src/pages/StockPage.test.tsx / src/pages/EtlStatusPage.test.tsx
└── scripts/
    ├── backfill.py                             # T1-5 新增（薄 CLI 包裝）
    ├── verify_prices.py                        # T1-7 新增
    └── m1_verify.sh                            # T1-7 新增
```

### 1.5 任務順序

```
T1-1 schema ─► T1-2 parser ─► T1-3 loader ─► T1-4 job/CLI/排程 ─► T1-5 回補腳本 ─► T1-6 API ─► T1-7 Web + 整合驗收
```

一次只做一個任務；前一個任務 Reviewer `APPROVE` 後才開始下一個。

---

## 2. 資料來源與端點（本里程碑唯一認可的來源）

| 用途 | 端點 | 參數 | 回應形狀 | 備註 |
| --- | --- | --- | --- | --- |
| 上市日成交（全市場、可指定日期） | `https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX` | `date=YYYYMMDD`、`type=ALLBUT0999`、`response=json` | `{"stat":"OK","date":…,"tables":[{"title","fields","data"},…]}` | 一次拿全市場；含權證以外全部證券，非個股由 loader 過濾 |
| 上櫃日成交（全市場、可指定日期） | `https://www.tpex.org.tw/www/zh-tw/afterTrading/otc` | `date=YYYY/MM/DD`、`type=EW`、`response=json` | 同上 `tables` 信封 | **本里程碑風險最高的端點**；失敗時自動退回下一列 |
| 上櫃日成交（舊版備援） | `https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php` | `l=zh-tw`、`d=RRR/MM/DD`（民國）、`o=json` | `{"reportDate":"115/09/18","aaData":[[…],…]}` | 欄位靠固定順序 |
| 加權指數日 K（整月） | `https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST` | `date=YYYYMM01`、`response=json` | `{"stat":"OK","fields":[…],"data":[[…]]}`（單表，頂層） | 一次一個月 → 5 年只要 60 次請求 |
| 除權除息計算結果表（上市） | `https://www.twse.com.tw/rwd/zh/exRight/TWT49U` | `startDate=YYYYMMDD`、`endDate=YYYYMMDD`、`response=json` | 單表或 `tables` 信封 | 一次最多查一個月 |

上櫃除權息**不在 M1 範圍**（見 §6 範圍邊界）。

## 3. M1 資料表 DDL（T1-1 實作，其他任務查閱用）

```sql
-- 日 K（未還原原始價）。hypertable，按月分區。
CREATE TABLE daily_price (
    stock_id     VARCHAR(10)   NOT NULL,
    trade_date   DATE          NOT NULL,
    open         NUMERIC(12,4),
    high         NUMERIC(12,4),
    low          NUMERIC(12,4),
    close        NUMERIC(12,4),
    change       NUMERIC(12,4),              -- 漲跌價差，含正負號；無法判斷時為 NULL
    volume       BIGINT        NOT NULL DEFAULT 0,   -- 成交股數（股，不是張）
    turnover     NUMERIC(20,0) NOT NULL DEFAULT 0,   -- 成交金額（元）
    transactions BIGINT        NOT NULL DEFAULT 0,   -- 成交筆數
    source       VARCHAR(8)    NOT NULL,             -- TWSE / TPEx
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_id, trade_date),
    CONSTRAINT ck_daily_price_source CHECK (source IN ('TWSE', 'TPEx'))
);
CREATE INDEX ix_daily_price_trade_date ON daily_price (trade_date);
-- 之後轉 hypertable：create_hypertable_if_available(conn, "daily_price", "trade_date", "1 month")

-- 指數日 K。hypertable，按月分區。
CREATE TABLE index_daily (
    index_id     VARCHAR(16)   NOT NULL,             -- M1 只有 'TAIEX'
    trade_date   DATE          NOT NULL,
    open         NUMERIC(14,2),
    high         NUMERIC(14,2),
    low          NUMERIC(14,2),
    close        NUMERIC(14,2),
    volume       BIGINT,                             -- M1 一律 NULL
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, trade_date)
);
CREATE INDEX ix_index_daily_trade_date ON index_daily (trade_date);
-- create_hypertable_if_available(conn, "index_daily", "trade_date", "1 year")

-- 除權息還原係數（事件表，不是 hypertable）。
CREATE TABLE adj_factor (
    stock_id        VARCHAR(10)   NOT NULL,
    ex_date         DATE          NOT NULL,          -- 除權息交易日
    factor          NUMERIC(12,8) NOT NULL,          -- 除權息參考價 ÷ 除權息前收盤價
    prev_close      NUMERIC(12,4),
    reference_price NUMERIC(12,4),
    cash_dividend   NUMERIC(12,6),                   -- M1 一律 NULL，留給 M3
    stock_dividend  NUMERIC(12,6),                   -- M1 一律 NULL，留給 M3
    kind            VARCHAR(8),                      -- 除息 / 除權 / 除權息
    source          VARCHAR(8)    NOT NULL,          -- M1 一律 'TWSE'
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_id, ex_date),
    CONSTRAINT ck_adj_factor_positive CHECK (factor > 0)
);
CREATE INDEX ix_adj_factor_ex_date ON adj_factor (ex_date);

-- ETL 執行紀錄（維運頁與斷點續傳都靠它）。
CREATE TABLE etl_job_log (
    job_id       BIGSERIAL     PRIMARY KEY,
    job_name     VARCHAR(64)   NOT NULL,             -- 見 §4 job 名稱表
    target_date  DATE,                               -- 以「日」為單位的 job 用
    target_key   VARCHAR(64),                        -- 其他 job 用（年份、市場、YYYY-MM、區間）
    status       VARCHAR(16)   NOT NULL,             -- running / success / failed / skipped
    rows         INTEGER       NOT NULL DEFAULT 0,
    error        TEXT,
    started_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    CONSTRAINT ck_etl_job_log_status CHECK (status IN ('running','success','failed','skipped'))
);
CREATE INDEX ix_etl_job_log_name_started ON etl_job_log (job_name, started_at DESC);
CREATE INDEX ix_etl_job_log_lookup      ON etl_job_log (job_name, target_date, target_key, status);
```

`open` / `high` / `low` / `close` / `change` 在 PostgreSQL 16 都是非保留字，**可以不加引號**（Architect 已在本機 PostgreSQL 16 實測 `CREATE TABLE` + `SELECT` 通過）。

## 4. job 名稱（全專案唯一，T1-3 之後都用這組字串）

| `job_name` | 由誰寫入 | `target_date` | `target_key` | 說明 |
| --- | --- | --- | --- | --- |
| `stock_list_twse` / `stock_list_tpex` | 排程、CLI | NULL | 市場別 | M0 的個股清單刷新 |
| `trading_calendar` | 排程、CLI | NULL | 年份字串，例 `2026` | 官方休市日 → 日曆 |
| `calendar_from_index` | CLI、回補腳本 | NULL | 年份字串 | 由 TAIEX 指數反推歷史年度日曆（`rebuild_calendar_from_index` 自己記，T1-5 不要再包一層） |
| `daily_price_twse` / `daily_price_tpex` | 排程、CLI、回補腳本 | 交易日 | NULL | **每日與回補共用同一個名稱**，斷點續傳才有效 |
| `index_daily_taiex` | 排程、CLI、回補腳本 | NULL | `YYYY-MM` | 指數以「月」為單位 |
| `adj_factor_twse` | 排程、CLI、回補腳本 | NULL | `YYYYMMDD-YYYYMMDD` | 除權息以「區間」為單位 |

## 5. API 契約（T1-6 實作，T1-7 查閱用）

所有端點都在 `/api` 底下、同源、不開 CORS。日期一律 `YYYY-MM-DD` 字串；價格一律 JSON 數字（後端由 `Decimal` 轉 `float`，四捨五入到小數第 4 位）。

### 5.1 `GET /api/stocks/{stock_id}`

```json
{
  "stock_id": "2330",
  "name": "台積電",
  "market": "TWSE",
  "industry": "半導體業",
  "listed_date": "1994-09-05",
  "is_etf": false,
  "is_active": true,
  "latest": {
    "time": "2026-09-18", "open": 996.0, "high": 1010.0, "low": 995.0,
    "close": 1008.0, "change": 13.0, "volume": 30000000,
    "turnover": 30000000000, "transactions": 35000
  }
}
```
`latest` 在沒有任何日 K 時為 `null`。查無此代號 → `404 {"detail":"查無此個股：9999"}`。

### 5.2 `GET /api/stocks/{stock_id}/prices`

查詢參數：

| 參數 | 型別 | 預設 | 說明 |
| --- | --- | --- | --- |
| `from` | `YYYY-MM-DD` | `to` 往前 365 天 | 含當日 |
| `to` | `YYYY-MM-DD` | 該股在 `daily_price` 的最新 `trade_date`；完全沒資料時為台北時間今天 | 含當日 |
| `adj` | bool | `false` | `true` 套用還原係數 |
| `limit` | int 1–6000 | 2000 | 超過時取**最新的** `limit` 筆 |

```json
{
  "stock_id": "2330",
  "name": "台積電",
  "market": "TWSE",
  "adjusted": true,
  "from": "2026-09-16",
  "to": "2026-09-18",
  "count": 3,
  "items": [
    {"time":"2026-09-16","open":985.05,"high":994.95,"low":980.1,"close":990.0,"change":4.95,"volume":25000000,"turnover":25000000000,"transactions":30000},
    {"time":"2026-09-17","open":992.0,"high":998.0,"low":988.0,"close":995.0,"change":-5.0,"volume":20000000,"turnover":19900000000,"transactions":25000},
    {"time":"2026-09-18","open":996.0,"high":1010.0,"low":995.0,"close":1008.0,"change":13.0,"volume":30000000,"turnover":30000000000,"transactions":35000}
  ]
}
```

- `items` 依 `time` **升冪**排序（Lightweight Charts 要求）。
- `adj=true` 時只調整 `open`/`high`/`low`/`close`/`change`，**不調整** `volume`/`turnover`/`transactions`。
- 錯誤：`from > to` → `422`；日期格式錯 → `422`；個股不存在 → `404`。個股存在但區間內無資料 → `200` 且 `count: 0`、`items: []`。

### 5.3 `GET /api/indices/{index_id}/prices`

`index_id` 白名單只有 `TAIEX`（大小寫不敏感，一律正規化為大寫）；其他 → `404`。參數同 5.2 的 `from`/`to`/`limit`（沒有 `adj`）。

```json
{"index_id":"TAIEX","name":"發行量加權股價指數","from":"2026-09-16","to":"2026-09-18","count":3,
 "items":[{"time":"2026-09-16","open":24500.0,"high":24680.0,"low":24450.0,"close":24600.0},
          {"time":"2026-09-17","open":24610.0,"high":24700.0,"low":24560.0,"close":24650.0},
          {"time":"2026-09-18","open":24660.0,"high":24800.0,"low":24640.0,"close":24780.0}]}
```

### 5.4 `GET /api/etl/jobs?limit=50`（`limit` 1–500，預設 50）

依 `started_at` 降冪。

```json
{"count":1,"items":[
  {"job_id":128,"job_name":"daily_price_twse","target_date":"2026-09-18","target_key":null,
   "status":"success","rows":1043,"error":null,
   "started_at":"2026-09-18T15:31:02+08:00","finished_at":"2026-09-18T15:31:09+08:00",
   "duration_seconds":7.0}]}
```

### 5.5 `GET /api/etl/summary`

每個出現過的 `job_name` 一列，依 `job_name` 升冪。

```json
{"count":1,"items":[
  {"job_name":"daily_price_twse","last_status":"success","last_target_date":"2026-09-18",
   "last_target_key":null,"last_rows":1043,
   "last_started_at":"2026-09-18T15:31:02+08:00","last_finished_at":"2026-09-18T15:31:09+08:00",
   "failed_last_7_days":0,"total_runs":128}]}
```

---

## T1-1　Migration 0002：價格三表 + etl_job_log，與 hypertable 雙簽名

### 目標

建立 M1 的四張表、更新 `tables.py`、把 `create_hypertable_if_available()` 改成能同時相容新舊 TimescaleDB 簽名，並補上 hypertable 建立路徑的測試（解 M0 的 U-2）。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `db/migrations/versions/0002_price_tables.py` | 新增 |
| `db/twstock_db/tables.py` | 修改：新增 `daily_price`、`index_daily`、`adj_factor`、`etl_job_log` 四個 `Table` |
| `db/twstock_db/timescale.py` | 修改：`create_hypertable_if_available` 改為雙簽名 |
| `db/tests/test_db_hypertable.py` | 新增 |
| `db/tests/test_db_migrations.py` | 修改：`TestTablesExist` 與 `TestReversibility` 補上四張新表 |
| `conftest.py` | 修改：`clean_db` 的 TRUNCATE 加 `RESTART IDENTITY CASCADE` |

### 1. `tables.py`

在檔案結尾追加四個 `Table`，欄位名稱、型別、`nullable`、`server_default` 必須與 §3 DDL **逐欄一致**。型別對照：

| DDL | SQLAlchemy |
| --- | --- |
| `VARCHAR(n)` | `String(n)` |
| `DATE` | `Date()` |
| `NUMERIC(p,s)` | `Numeric(p, s)` |
| `BIGINT` | `BigInteger()` |
| `INTEGER` | `Integer()` |
| `TEXT` | `Text()` |
| `TIMESTAMPTZ NOT NULL DEFAULT now()` | `DateTime(timezone=True), nullable=False, server_default=func.now()` |
| `BIGSERIAL PRIMARY KEY` | `Column("job_id", BigInteger(), primary_key=True, autoincrement=True)` |

`daily_price` 與 `index_daily` 的主鍵用兩個 `primary_key=True` 欄位表示複合主鍵。CHECK 用 `CheckConstraint(..., name=...)`，名稱照 DDL。

`etl_job_log` 有一個欄位叫 `rows`——`Table` 物件本身沒有 `rows` 屬性衝突，直接 `Column("rows", Integer(), ...)` 即可，程式中用 `etl_job_log.c.rows` 存取。

### 2. `timescale.py`：hypertable 雙簽名

把 `create_hypertable_if_available` 換成下面這份（其餘函式不動）：

```python
def create_hypertable_if_available(
    conn: Connection, table: str, time_column: str, chunk_interval: str = "1 month"
) -> bool:
    """若已安裝 timescaledb，將 table 轉為 hypertable 並回傳 True；否則不做事回傳 False。

    先用 TimescaleDB 2.13+ 的 by_range() 簽名，失敗時退回 2.13 之前的舊簽名。
    """
    identifier_pattern = re.compile(r"^[a-z_][a-z0-9_]*$")
    if not identifier_pattern.match(table) or not identifier_pattern.match(time_column):
        raise ValueError(f"無效的識別字：table={table!r}, time_column={time_column!r}")

    if not timescaledb_installed(conn):
        logger.info("未安裝 TimescaleDB，%s 維持一般資料表", table)
        return False

    params = {"table": table, "time_column": time_column, "interval": chunk_interval}
    try:
        with conn.begin_nested():
            conn.execute(text(NEW_HYPERTABLE_SQL), params)
        logger.info("已將 %s 轉為 hypertable（by_range 簽名）", table)
        return True
    except DBAPIError as exc:  # noqa: BLE001 - 舊版 TimescaleDB 沒有 by_range()
        logger.warning("by_range() 簽名失敗，改用舊簽名重試：%s", exc)

    with conn.begin_nested():
        conn.execute(text(LEGACY_HYPERTABLE_SQL), params)
    logger.info("已將 %s 轉為 hypertable（舊簽名）", table)
    return True
```

模組層常數（放在 `logger = ...` 之下）：

```python
NEW_HYPERTABLE_SQL = """
SELECT create_hypertable(
    CAST(:table AS regclass),
    by_range(CAST(:time_column AS name), CAST(:interval AS interval)),
    if_not_exists => TRUE,
    migrate_data  => TRUE
)
"""

LEGACY_HYPERTABLE_SQL = """
SELECT create_hypertable(
    CAST(:table AS regclass), :time_column,
    chunk_time_interval => CAST(:interval AS interval),
    if_not_exists => TRUE,
    migrate_data  => TRUE
)
"""
```

`from sqlalchemy.exc import DBAPIError` 要加進 import。`conn.begin_nested()` 是 SAVEPOINT，讓第一次失敗不會把整個 migration 交易弄髒。

### 3. Migration `0002_price_tables.py`

- `revision = "0002"`、`down_revision = "0001"`、docstring 第一行 `create price tables and etl_job_log`。
- `upgrade()`：依序 `op.create_table` 四張表 → `op.create_index` 四個索引 → 呼叫
  `create_hypertable_if_available(op.get_bind(), "daily_price", "trade_date", "1 month")` 與
  `create_hypertable_if_available(op.get_bind(), "index_daily", "trade_date", "1 year")`。
- `downgrade()`：`op.drop_table("etl_job_log")`、`"adj_factor"`、`"index_daily"`、`"daily_price"`（索引隨表一起消失，不必個別 drop）。
- 不要呼叫 `ensure_timescaledb()`（0001 已經做過）。

### 4. `conftest.py` 修改

`clean_db` 內的 TRUNCATE 改成：

```python
conn.execute(text(f"TRUNCATE {', '.join(table_names)} RESTART IDENTITY CASCADE"))
```

理由：`etl_job_log.job_id` 是 BIGSERIAL，不重設序號會讓測試之間互相影響。

### 5. 測試

`db/tests/test_db_hypertable.py`：

1. `test_create_hypertable_uses_by_range_first`：用 `unittest.mock.MagicMock()` 當 `conn`，`monkeypatch.setattr(timescale, "timescaledb_installed", lambda c: True)`。呼叫 `create_hypertable_if_available(conn, "daily_price", "trade_date", "1 month")`，斷言
   - 回傳 `True`
   - `conn.execute` 被呼叫 1 次
   - 第一個位置參數轉成 `str()` 後含 `by_range`
   - 第二個位置參數 == `{"table": "daily_price", "time_column": "trade_date", "interval": "1 month"}`
2. `test_create_hypertable_falls_back_to_legacy`：同上，但讓 `conn.execute` 第一次拋 `DBAPIError("stmt", {}, Exception("function by_range does not exist"))`、第二次正常。斷言回傳 `True`、`conn.execute` 被呼叫 2 次、第二次 SQL 含 `chunk_time_interval`。
3. `test_create_hypertable_skipped_without_extension`（需要 DB，用 `db_engine`）：若 `timescaledb_installed()` 為 True 就 `pytest.skip("此 PostgreSQL 已安裝 TimescaleDB")`；否則斷言 `create_hypertable_if_available(conn, "daily_price", "trade_date")` 回傳 `False`，且 `daily_price` 仍可正常 INSERT。
4. `test_hypertables_registered_when_timescale_installed`（需要 DB）：若 `timescaledb_installed()` 為 False 就
   `pytest.skip("此 PostgreSQL 未安裝 TimescaleDB，hypertable 實跑留待使用者本機驗證")`；
   否則查 `SELECT hypertable_name FROM timescaledb_information.hypertables` 應含 `daily_price`、`index_daily`。

`db/tests/test_db_migrations.py`：`test_tables_exist` 補上四張新表名；新增 `test_daily_price_source_check`（插入 `source='XXX'` 應 `IntegrityError`）與 `test_adj_factor_positive_check`（`factor=0` 應 `IntegrityError`）。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed；skipped 只會出現「此 PostgreSQL 未安裝 TimescaleDB…」那一筆

cd /home/claude/TwStock && export DATABASE_URL=$(scripts/pg_temp.sh start) && \
  .venv/bin/alembic -c db/alembic.ini downgrade base && .venv/bin/alembic -c db/alembic.ini upgrade head && echo REVERSIBLE_OK
# 預期：最後一行 REVERSIBLE_OK，中途出現 "TimescaleDB 不可用，維持一般資料表" 與兩行 "未安裝 TimescaleDB，… 維持一般資料表"

cd /home/claude/TwStock && export DATABASE_URL=$(scripts/pg_temp.sh start) && \
  /usr/lib/postgresql/16/bin/psql "${DATABASE_URL/postgresql+psycopg/postgresql}" -c '\d daily_price' -c '\d etl_job_log'
# 預期：欄位與 §3 DDL 逐欄一致
```

### 不要做的事

- 不要建 continuous aggregate（週 K／月 K）與壓縮政策——那是 M2 之後的事。
- 不要加 `daily_price → stock` 的外鍵（見 D-017）。
- 不要改 `0001` migration。
- 不要在這個任務寫任何 ETL／API／前端程式。

---

## T1-2　來源 parser：日成交（上市／上櫃）、加權指數、除權除息

### 目標

寫出四組純函式 parser 與共用的 JSON 報表信封工具、數值清洗工具，並建立離線 fixture。**這個任務完全不碰資料庫。**

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `etl/twstock_etl/numbers.py` | 新增 |
| `etl/twstock_etl/sources/report.py` | 新增 |
| `etl/twstock_etl/sources/twse_price.py` | 新增 |
| `etl/twstock_etl/sources/tpex_price.py` | 新增 |
| `etl/twstock_etl/sources/twse_index.py` | 新增 |
| `etl/twstock_etl/sources/twse_exright.py` | 新增 |
| `etl/twstock_etl/models.py` | 修改：追加三個 dataclass |
| `etl/tests/fixtures/*.json` | 新增 9 個（見 §6） |
| `etl/tests/fixtures/README.md` | 修改：補上新 fixture 的來源與日期 |
| `etl/tests/test_etl_numbers.py`、`test_etl_twse_price.py`、`test_etl_tpex_price.py`、`test_etl_twse_index.py`、`test_etl_twse_exright.py` | 新增 |

### 1. `models.py` 追加

```python
from decimal import Decimal

@dataclass(frozen=True)
class PriceRecord:
    """個股日成交紀錄（未還原原始價）。"""

    stock_id: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    change: Decimal | None      # 含正負號；無法判斷符號時為 None
    volume: int                 # 成交股數
    turnover: Decimal           # 成交金額（元）
    transactions: int           # 成交筆數
    source: str                 # "TWSE" 或 "TPEx"


@dataclass(frozen=True)
class IndexRecord:
    """指數日 K 紀錄。"""

    index_id: str               # M1 只有 "TAIEX"
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None = None   # M1 一律 None


@dataclass(frozen=True)
class AdjFactorRecord:
    """除權息還原係數紀錄。"""

    stock_id: str
    ex_date: date
    factor: Decimal             # 除權息參考價 ÷ 除權息前收盤價，8 位小數
    prev_close: Decimal | None
    reference_price: Decimal | None
    kind: str | None            # 除息 / 除權 / 除權息
    source: str = "TWSE"
```

### 2. `numbers.py`

```python
NULL_TOKENS = frozenset({"", "-", "--", "---", "X", "x", "N/A", "n/a", "null", "None", "免評", "不適用"})
_TAG_RE = re.compile(r"<[^>]*>")

def clean_cell(value: object) -> str:
    """把報表儲存格轉成乾淨字串：去 HTML 標籤、去千分位逗號、去全形空白與前後空白、去加號。"""

def parse_decimal(value: object) -> Decimal | None:
    """把儲存格轉成 Decimal；空值或 NULL_TOKENS 回傳 None。

    Raises:
        SourceFormatError: 清洗後既不是空值也不是合法數字
    """

def parse_int(value: object) -> int | None:
    """把儲存格轉成 int（先走 parse_decimal 再取整數部分）；空值回傳 None。"""

def parse_sign(value: object) -> int:
    """解析 TWSE 的「漲跌(+/-)」欄位，回傳 1 / -1 / 0。

    清洗後含 '+' → 1；含 '-' → -1；其餘（含 'X'、空字串）→ 0。
    """
```

`clean_cell` 的順序：`str(value)` → 移除 `_TAG_RE` 匹配到的標籤 → `replace("　", "")` → `replace(",", "")` → `strip()` → 若開頭是 `+` 就去掉。
注意 **不要**去掉開頭的 `-`（那是負號），但 `clean_cell("--")` 結果仍是 `"--"`，會被 `NULL_TOKENS` 攔下。

### 3. `sources/report.py`

```python
def find_field(fields: Sequence[str], *candidates: str) -> int:
    """在 fields 中找欄位索引：先找完全相符，再找以 candidate 開頭的欄位。

    Raises:
        SourceFormatError: 都找不到
    """

def extract_table(
    payload: object, required_fields: Sequence[str]
) -> tuple[list[str], list[list[object]]]:
    """從 TWSE / TPEx 報表 JSON 取出含指定欄位的表格，回傳 (fields, data)。

    支援三種形狀：
    1. {"tables": [{"fields": [...], "data": [[...]]}, ...]}  → 取第一個欄位滿足的表
    2. {"fields": [...], "data": [[...]]}                      → 頂層單表
    3. {"fields": [...], "aaData": [[...]]}                    → 頂層單表（舊式鍵名）

    「欄位滿足」的判定：required_fields 中每一個都能用 find_field 在該表 fields 內找到。

    Raises:
        SourceFormatError: payload 不是 dict、stat 不是 OK、找不到符合的表、data 為空
    """

def is_no_trade(volume: int, close: "Decimal | None") -> bool:
    """判斷是否為「當日無成交」：成交股數為 0 且收盤價為空或 0。"""
```

`extract_table` 的 `stat` 檢查：`payload.get("stat")` 存在且 `str(...).upper() not in {"OK", "很抱歉，沒有符合條件的資料!"}`…
→ 簡化成：若 `stat` 存在且 `str(stat).strip().upper() != "OK"`，拋
`SourceFormatError(f"來源回應 stat 非 OK：{stat}")`。

### 4. `sources/twse_price.py`

```python
TWSE_DAILY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TWSE_PRICE_FIELDS = ("證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額",
                     "開盤價", "最高價", "最低價", "收盤價", "漲跌價差")

def fetch_twse_daily(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上市每日收盤行情 JSON。"""
    # params = {"date": trade_date.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"}
    # 用 twstock_etl.http.default_client / get_with_retry；client 為 None 時自建並在 finally 關閉
    # 回應不是 dict → SourceFormatError

def parse_twse_daily(payload: dict, trade_date: date) -> list[PriceRecord]:
    """把上市每日收盤行情 JSON 轉成 PriceRecord 清單（source="TWSE"）。"""
```

`parse_twse_daily` 規則：

1. `fields, data = extract_table(payload, TWSE_PRICE_FIELDS)`。
2. 用 `find_field` 取得各欄索引；漲跌符號欄用 `find_field(fields, "漲跌(+/-)", "漲跌")`，**找不到就當作沒有符號欄**（`sign = 0`，此時 `change = None`）。
3. 逐列：
   - `stock_id = clean_cell(row[i_code])`；為空或不符 `^[0-9A-Z]{4,6}$` → 跳過（DEBUG log）。
   - `volume = parse_int(row[i_volume]) or 0`、`transactions = parse_int(...) or 0`、`turnover = parse_decimal(...) or Decimal(0)`。
   - `open/high/low/close = parse_decimal(...)`。
   - `if is_no_trade(volume, close): continue`（DEBUG log，不算錯）。
   - `diff = parse_decimal(row[i_change])`；`sign = parse_sign(row[i_sign])`；
     `change = diff * sign if (diff is not None and sign != 0) else None`。
   - 產生 `PriceRecord(..., trade_date=trade_date, source="TWSE")`。
4. 解析後一筆都沒有 → `SourceFormatError(f"{trade_date} 上市日成交解析結果為空")`。
5. 單列解析失敗（`parse_decimal` 拋 `SourceFormatError`）→ **整批失敗**，讓例外往上拋；不要 try/except 吞掉。

### 5. `sources/tpex_price.py`

```python
TPEX_DAILY_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
TPEX_DAILY_URL_LEGACY = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php"
TPEX_PRICE_FIELDS = ("代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低",
                     "成交股數", "成交金額", "成交筆數")
LEGACY_COLUMNS = ("代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低",
                  "成交股數", "成交金額", "成交筆數", "最後買價", "最後買量",
                  "最後賣價", "最後賣量", "發行股數", "次日漲停價", "次日跌停價")

def fetch_tpex_daily(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上櫃每日收盤行情 JSON；新版端點失敗時自動退回舊版端點。"""

def parse_tpex_daily(payload: dict, trade_date: date) -> list[PriceRecord]:
    """把上櫃每日收盤行情 JSON 轉成 PriceRecord 清單（source="TPEx"）。"""
```

- `fetch_tpex_daily`：先試 `TPEX_DAILY_URL`，`params = {"date": trade_date.strftime("%Y/%m/%d"), "type": "EW", "response": "json"}`；
  若 `httpx.HTTPError` 或回應 JSON 解析失敗或 `parse_tpex_daily` 會用到的表格不存在（用 `extract_table` 試一次，抓 `SourceFormatError`），
  則記 `warning`，改試 `TPEX_DAILY_URL_LEGACY`，`params = {"l": "zh-tw", "d": f"{trade_date.year - 1911}/{trade_date:%m/%d}", "o": "json"}`。
  兩個都失敗 → 拋最後一個例外。
- `parse_tpex_daily` 先判斷形狀：
  - `payload` 有 `"aaData"` 且**沒有** `"fields"` → 舊式：`fields = list(LEGACY_COLUMNS)`、`data = payload["aaData"]`；
    若 `payload.get("reportDate")` 存在，用 `parse_tw_date` 解析後與 `trade_date` 比對，不符 → `SourceFormatError`。
  - 否則 → `fields, data = extract_table(payload, TPEX_PRICE_FIELDS)`；若 `payload.get("date")` 存在同樣比對日期。
- 逐列規則與 TWSE 相同，差別：上櫃「漲跌」欄本身就含正負號，所以 `change = parse_decimal(row[i_change])`，不需要符號欄。
- 「無成交」列在上櫃多半是 `"0.00"` 而不是 `"--"`，靠 `is_no_trade` 處理。

### 6. `sources/twse_index.py`

```python
TAIEX_HIST_URL = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST"
TAIEX_INDEX_ID = "TAIEX"
TAIEX_FIELDS = ("日期", "開盤指數", "最高指數", "最低指數", "收盤指數")

def fetch_taiex_month(year: int, month: int, client: httpx.Client | None = None) -> dict:
    """下載某年某月的發行量加權股價指數歷史資料 JSON。"""
    # params = {"date": f"{year:04d}{month:02d}01", "response": "json"}

def parse_taiex_month(payload: dict, year: int, month: int) -> list[IndexRecord]:
    """把加權指數歷史 JSON 轉成 IndexRecord 清單，並過濾成只有指定年月。"""
```

- 日期欄是民國 `115/09/18`，用既有的 `parse_tw_date` 解析。
- 只保留 `d.year == year and d.month == month` 的列；過濾後為空 → `SourceFormatError(f"加權指數資料不含 {year}-{month:02d}")`。
- `IndexRecord(index_id="TAIEX", volume=None, ...)`，依 `trade_date` 升冪排序回傳。

### 7. `sources/twse_exright.py`

```python
EXRIGHT_URL = "https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
EXRIGHT_FIELDS = ("資料日期", "股票代號", "除權息前收盤價", "除權息參考價")

def fetch_exright(start: date, end: date, client: httpx.Client | None = None) -> dict:
    """下載指定區間的除權除息計算結果表 JSON。"""
    # params = {"startDate": start.strftime("%Y%m%d"), "endDate": end.strftime("%Y%m%d"), "response": "json"}

def parse_exright(payload: dict) -> list[AdjFactorRecord]:
    """把除權除息計算結果表 JSON 轉成 AdjFactorRecord 清單。"""
```

- 欄位索引：`資料日期`（民國）、`股票代號`、`除權息前收盤價`、`除權息參考價`；
  `kind` 用 `find_field(fields, "除權息")`，找不到就 `kind = None`（**不要因此報錯**）。
- `factor = (reference_price / prev_close).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)`。
- 跳過並記 `warning` 的情況：`prev_close` 或 `reference_price` 為 `None`、`<= 0`。
- `stock_id` 不符 `^[0-9A-Z]{4,6}$` → 跳過。
- 全部被跳過 → 回傳空 list（**不報錯**，因為某些月份本來就沒有除權息）。
- 依 `(ex_date, stock_id)` 升冪排序回傳。

### 8. Fixture（手寫，依官方公開格式；一律 UTF-8）

全部放在 `etl/tests/fixtures/`。`TWSE_price_*.json` 與 `TPEx_price_*.json` 之後也被 T1-5 的 `--source-dir` 離線模式使用，**檔名不可改**。

`TWSE_price_20260918.json`（`20260916`、`20260917` 兩份結構相同，只換數字；三份都要建）：

```json
{
  "stat": "OK",
  "date": "20260918",
  "title": "115年09月18日 每日收盤行情(全部(不含權證、牛熊證))",
  "tables": [
    {
      "title": "價格指數(臺灣證券交易所)",
      "fields": ["指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)"],
      "data": [["寶島股價指數", "28,000.00", "<p style= color:red>+</p>", "100.00", "0.36"]],
      "notes": []
    },
    {
      "title": "每日收盤行情(全部(不含權證、牛熊證))",
      "fields": ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差", "最後揭示買價", "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比"],
      "data": [
        ["1101", "台泥", "10,000,000", "3,500", "372,000,000", "37.05", "37.30", "36.95", "37.20", "<p style= color:red>+</p>", "0.20", "37.15", "100", "37.20", "200", "15.40"],
        ["2317", "鴻海", "40,000,000", "20,000", "8,000,000,000", "199.00", "201.00", "198.00", "200.00", "<p style= color:red>+</p>", "1.00", "199.50", "60", "200.00", "70", "12.00"],
        ["2330", "台積電", "30,000,000", "35,000", "30,000,000,000", "996.00", "1,010.00", "995.00", "1,008.00", "<p style= color:red>+</p>", "13.00", "1,007.00", "40", "1,008.00", "50", "22.50"],
        ["2834", "臺企銀", "0", "0", "0", "--", "--", "--", "--", "X", "0.00", "--", "0", "--", "0", "0.00"],
        ["2882", "國泰金", "8,000,000", "5,000", "560,000,000", "69.50", "70.20", "69.40", "70.00", "<p style= color:red>+</p>", "0.50", "69.90", "30", "70.00", "40", "11.30"],
        ["0050", "元大台灣50", "9,000,000", "9,500", "1,822,500,000", "201.50", "203.00", "201.00", "202.50", "<p style= color:green>-</p>", "0.50", "202.45", "10", "202.50", "20", "0.00"]
      ],
      "notes": []
    }
  ]
}
```

三天的 TWSE 數值（其餘欄位自行填合理值，**收盤價與成交股數必須完全照表**）：

| 日期 | 1101 收盤 | 2317 收盤 | 2330 開/高/低/收 | 2834 | 2882 收盤 | 0050 收盤 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-16 | 36.80 | 198.00 | 995.00 / 1,005.00 / 990.00 / **1,000.00** | 無成交 | 69.00 | 200.00 |
| 2026-09-17 | 37.00 | 199.00 | 992.00 / 998.00 / 988.00 / **995.00** | 無成交 | 69.50 | 201.00 |
| 2026-09-18 | 37.20 | 200.00 | 996.00 / 1,010.00 / 995.00 / **1,008.00** | 無成交 | 70.00 | 202.50 |

2330 三天的成交股數依序 `25,000,000`、`20,000,000`、`30,000,000`；成交筆數 `30,000` / `25,000` / `35,000`；成交金額 `25,000,000,000` / `19,900,000,000` / `30,000,000,000`。
2026-09-17 的 2330 漲跌符號用綠色減號（`"<p style= color:green>-</p>"`、漲跌價差 `"5.00"`）。

`TPEx_price_20260918.json`（`20260916`、`20260917` 同樣三份）：

```json
{
  "stat": "ok",
  "date": "2026/09/18",
  "tables": [
    {
      "title": "上櫃股票每日收盤行情(不含定價)",
      "fields": ["代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "成交股數", "成交金額(元)", "成交筆數", "最後買價", "最後買量(千股)", "最後賣價", "最後賣量(千股)", "發行股數", "次日漲停價", "次日跌停價"],
      "data": [
        ["3105", "穩懋", "349.00", "-3.00", "351.00", "353.00", "348.00", "2,800,000", "980,000,000", "2,300", "348.50", "10", "349.00", "8", "2,000,000,000", "383.50", "314.50"],
        ["8069", "元太", "28.30", "-0.20", "28.50", "28.60", "28.20", "4,500,000", "127,350,000", "1,100", "28.25", "50", "28.30", "60", "1,140,000,000", "31.10", "25.50"],
        ["5347", "世界", "0.00", "0.00", "0.00", "0.00", "0.00", "0", "0", "0", "--", "0", "--", "0", "600,000,000", "0.00", "0.00"],
        ["1258", "其昌", "45.00", "0.50", "44.80", "45.20", "44.70", "500,000", "22,500,000", "300", "44.95", "5", "45.00", "5", "80,000,000", "49.50", "40.50"],
        ["006201", "元大富櫃50", "25.05", "-0.05", "25.10", "25.15", "25.00", "120,000", "3,006,000", "60", "25.00", "5", "25.05", "5", "50,000,000", "27.55", "22.55"]
      ]
    }
  ]
}
```

三天的 TPEx 收盤：3105 `350.00` / `352.00` / `349.00`；8069 `28.00` / `28.50` / `28.30`；006201 `25.00` / `25.10` / `25.05`；
`5347` 三天都是無成交；`1258 其昌` 三天都有成交（它**不在** `stock` 表裡，用來驗證 loader 的未知代號過濾）。

`TPEx_price_legacy_sample.json`（只給單元測試用，不進 `--source-dir` 流程）：

```json
{
  "stkNo": "",
  "reportDate": "115/09/18",
  "iTotalRecords": 2,
  "aaData": [
    ["3105", "穩懋", "349.00", "-3.00", "351.00", "353.00", "348.00", "2,800,000", "980,000,000", "2,300", "348.50", "10", "349.00", "8", "2,000,000,000", "383.50", "314.50"],
    ["5347", "世界", "0.00", "0.00", "0.00", "0.00", "0.00", "0", "0", "0", "--", "0", "--", "0", "600,000,000", "0.00", "0.00"]
  ]
}
```

`TAIEX_index_202609.json`：

```json
{
  "stat": "OK",
  "date": "20260901",
  "title": "115年09月 發行量加權股價指數歷史資料",
  "fields": ["日期", "開盤指數", "最高指數", "最低指數", "收盤指數"],
  "data": [
    ["115/09/16", "24,500.00", "24,680.00", "24,450.00", "24,600.00"],
    ["115/09/17", "24,610.00", "24,700.00", "24,560.00", "24,650.00"],
    ["115/09/18", "24,660.00", "24,800.00", "24,640.00", "24,780.00"]
  ],
  "notes": ["本資料僅供參考"]
}
```

`exright_20260901_20260930.json`：

```json
{
  "stat": "OK",
  "title": "115年09月 除權除息計算結果表",
  "fields": ["資料日期", "股票代號", "名稱", "除權息前收盤價", "除權息參考價", "權值+息值", "漲停價格", "跌停價格", "開盤競價基準", "減除股利參考價", "詳細資料", "最近一次申報資料 年/月/日", "最近一次申報每股(單位)淨值", "最近一次申報每股(單位)盈餘", "除權息"],
  "data": [
    ["115/09/16", "1101", "台泥", "36.20", "36.00", "0.20", "39.60", "32.40", "36.00", "36.00", "詳細資料", "115/08/14", "20.00", "2.00", "除息"],
    ["115/09/17", "2330", "台積電", "1,000.00", "990.00", "10.00", "1,089.00", "891.00", "990.00", "990.00", "詳細資料", "115/08/14", "150.00", "45.00", "除息"],
    ["115/09/18", "2317", "鴻海", "0.00", "0.00", "0.00", "0.00", "0.00", "0.00", "0.00", "詳細資料", "115/08/14", "80.00", "10.00", "除息"]
  ]
}
```

（`2317` 那列的前收盤價是 0，用來驗證「跳過並記 warning」。）

### 9. 測試

`test_etl_numbers.py`：`clean_cell("<p style= color:red>+</p>") == ""`、`parse_decimal("1,234.56") == Decimal("1234.56")`、
`parse_decimal("--") is None`、`parse_decimal("abc")` 拋 `SourceFormatError`、`parse_int("1,000") == 1000`、
`parse_sign("<p style= color:red>+</p>") == 1`、`parse_sign("<p style= color:green>-</p>") == -1`、`parse_sign("X") == 0`、
`parse_decimal("-1.5") == Decimal("-1.5")`。

`test_etl_twse_price.py`：
- 讀 `TWSE_price_20260918.json` → `parse_twse_daily(payload, date(2026,9,18))` 回傳 **5** 筆（2834 無成交被跳過）。
- 其中 `2330` 的 `close == Decimal("1008.00")`、`volume == 30000000`、`change == Decimal("13.00")`、`source == "TWSE"`。
- `0050` 的 `change == Decimal("-0.50")`（綠色減號）。
- 把 `data` 清空的 payload → 拋 `SourceFormatError`。
- `stat` 改成 `"很抱歉"` → 拋 `SourceFormatError`。
- `fetch_twse_daily` 用 `httpx.MockTransport` 驗證帶出的 `params` 是 `date=20260918&type=ALLBUT0999&response=json`。

`test_etl_tpex_price.py`：
- 新版 fixture → 4 筆（5347 被跳過），`3105.close == Decimal("349.00")`、`change == Decimal("-3.00")`。
- 舊版 fixture（`TPEx_price_legacy_sample.json`）→ 1 筆，`3105.close == Decimal("349.00")`。
- `reportDate` 與傳入日期不符 → 拋 `SourceFormatError`。
- `fetch_tpex_daily` 用 `MockTransport`：新版端點回 500、舊版端點回 legacy fixture → 仍能拿到可解析的 payload（驗證備援路徑）。

`test_etl_twse_index.py`：3 筆、`2026-09-18` 收盤 `Decimal("24780.00")`、`index_id == "TAIEX"`、`volume is None`；
要求 `parse_taiex_month(payload, 2026, 8)` 拋 `SourceFormatError`。

`test_etl_twse_exright.py`：2 筆；`2330` 的 `ex_date == date(2026,9,17)`、`factor == Decimal("0.99000000")`、`kind == "除息"`；
`1101` 的 `factor == Decimal("0.99447514")`；`2317` 不在結果內。

### 驗收指令

```bash
cd /home/claude/TwStock && .venv/bin/python -m pytest etl/tests -rs
# 預期：全部 passed，0 failed

cd /home/claude/TwStock && .venv/bin/python - <<'PY'
import json, pathlib
from datetime import date
from twstock_etl.sources.twse_price import parse_twse_daily
from twstock_etl.sources.tpex_price import parse_tpex_daily
from twstock_etl.sources.twse_index import parse_taiex_month
from twstock_etl.sources.twse_exright import parse_exright
f = pathlib.Path("etl/tests/fixtures")
tw = parse_twse_daily(json.loads((f/"TWSE_price_20260918.json").read_text()), date(2026,9,18))
tp = parse_tpex_daily(json.loads((f/"TPEx_price_20260918.json").read_text()), date(2026,9,18))
ix = parse_taiex_month(json.loads((f/"TAIEX_index_202609.json").read_text()), 2026, 9)
ex = parse_exright(json.loads((f/"exright_20260901_20260930.json").read_text()))
print("twse", len(tw), [r.close for r in tw if r.stock_id=="2330"])
print("tpex", len(tp), [r.close for r in tp if r.stock_id=="3105"])
print("index", len(ix), ix[-1].close)
print("exright", len(ex), [str(r.factor) for r in ex])
PY
# 預期輸出：
# twse 5 [Decimal('1008.00')]
# tpex 4 [Decimal('349.00')]
# index 3 24780.00
# exright 2 ['0.99447514', '0.99000000']
```

### 不要做的事

- 不要寫任何 SQL、不要 import `twstock_db`。
- 不要新增 pypi 套件（`pandas` 不要用）。
- 不要對真實網址發請求（本環境連不到，測試一律用 `httpx.MockTransport`）。
- 不要做上櫃的除權息、不要做櫃買指數（M1 範圍外）。

---

## T1-3　Loader：價格三表寫入、未知代號過濾、etl_job_log 紀錄

### 目標

把 T1-2 的 dataclass 寫進資料庫，並提供 `etl_job_log` 的「開始 / 成功 / 失敗 / 跳過」記錄機制與斷點續傳查詢。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `etl/twstock_etl/loaders/price.py` | 新增 |
| `etl/twstock_etl/loaders/job_log.py` | 新增 |
| `etl/twstock_etl/loaders/stock.py` | 修改：新增 `count_active_stocks` |
| `etl/tests/test_etl_price_loaders.py` | 新增 |
| `etl/tests/test_etl_job_log.py` | 新增 |

### 1. `loaders/price.py`

```python
BATCH_SIZE = 1000


@dataclass(frozen=True)
class PriceUpsertResult:
    """日 K 寫入結果。"""

    written: int          # 實際 upsert 的筆數
    skipped_unknown: int  # 因為 stock 表沒有該代號而被丟掉的筆數


def known_stock_ids(conn: Connection) -> set[str]:
    """回傳 stock 表內所有代號（含 is_active=false）。"""


def upsert_daily_prices(
    conn: Connection, records: Sequence[PriceRecord]
) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, trade_date) DO UPDATE 寫入日 K；stock 表沒有的代號略過。"""


def upsert_index_daily(conn: Connection, records: Sequence[IndexRecord]) -> int:
    """以 ON CONFLICT (index_id, trade_date) DO UPDATE 寫入指數日 K，回傳筆數。"""


def upsert_adj_factors(conn: Connection, records: Sequence[AdjFactorRecord]) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, ex_date) DO UPDATE 寫入還原係數；stock 表沒有的代號略過。"""


def count_prices(conn: Connection, trade_date: date, source: str) -> int:
    """回傳某交易日、某來源已寫入的日 K 筆數。"""


def index_trade_dates(conn: Connection, index_id: str, year: int) -> set[date]:
    """回傳某指數在某年份已有資料的所有 trade_date（給交易日曆回補用）。"""
```

實作要點：

- 全部用 `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update(...)`，分批 `BATCH_SIZE`。
- `set_` 內容：所有非主鍵欄位 + `updated_at: func.now()`。`adj_factor` 的 `cash_dividend`、`stock_dividend` M1 一律寫 `None`。
- `upsert_daily_prices` / `upsert_adj_factors` 先取 `known_stock_ids(conn)`，過濾後再寫；被丟掉的代號以 `logger.info("略過 %d 筆不在 stock 表的代號：%s", n, sample)` 記錄（`sample` 取前 5 個）。
- 記得 `Decimal` 可以直接交給 psycopg 寫進 `NUMERIC`，**不要**轉 `float`。
- `records` 為空 → 回傳 `PriceUpsertResult(0, 0)` / `0`，不執行 SQL。
- **同一批內若出現重複主鍵**（來源偶爾會重複列），`ON CONFLICT` 在同一個 INSERT 語句內會報
  `ON CONFLICT DO UPDATE command cannot affect row a second time`。所以寫入前先用 dict 以主鍵去重，
  **保留最後一筆**，並在有去重時記 `warning`。

### 2. `loaders/stock.py` 追加

```python
def count_active_stocks(conn: Connection, market: str) -> int:
    """回傳某市場目前 is_active=true 的個股筆數。"""
```

### 3. `loaders/job_log.py`

```python
logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 2000


class JobSkipped(Exception):
    """job 在執行中決定跳過（非開市日、已完成等），由 job_run 攔下並記為 skipped。"""


@dataclass
class JobRun:
    """一次 job 執行的可變狀態，由 job_run() yield 出來。"""

    job_id: int
    job_name: str
    rows: int = 0            # 呼叫端執行完把筆數寫回來
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


def has_successful_run(
    conn: Connection,
    job_name: str,
    *,
    target_date: date | None = None,
    target_key: str | None = None,
) -> bool:
    """該 job 的該目標是否已有 status 為 success 或 skipped 的紀錄。"""


def latest_run(conn: Connection, job_name: str) -> dict[str, Any] | None:
    """回傳該 job_name 最近一次執行的紀錄 dict；沒有回傳 None。"""
```

注意：`job_run` 的三次寫入（插入 running、更新結果）都要用**自己的 `engine.begin()` 交易**，
不能跟 job 主體共用交易，否則 job 失敗 rollback 會把 log 也 rollback 掉。

### 4. 測試（需要 DB，用 `clean_db` fixture）

`test_etl_price_loaders.py`：
- 先插入 `stock`（`2330`、`3105`）再 upsert 三筆 `PriceRecord`（含一筆 `9999`）→ `written == 2`、`skipped_unknown == 1`。
- 重跑同一批，改掉 `close` → `written == 2`，DB 內 `close` 是新值（驗證 upsert）。
- 同一批內出現兩筆 `(2330, 2026-09-18)` → 不報錯，DB 只有一列且是**後面那筆**的值。
- `upsert_index_daily` 寫 3 筆 → `count == 3`；`index_trade_dates(conn, "TAIEX", 2026)` 回傳 3 個日期。
- `upsert_adj_factors` 同樣驗證未知代號過濾。
- `count_prices(conn, date(2026,9,18), "TWSE")` 回傳正確筆數。

`test_etl_job_log.py`：
- 成功路徑：`with job_run(engine, "daily_price_twse", target_date=d) as run: run.rows = 42` →
  DB 內該列 `status='success'`、`rows=42`、`finished_at` 不是 NULL。
- 失敗路徑：內部 `raise RuntimeError("壞掉了")` → `pytest.raises(RuntimeError)`，DB 內 `status='failed'`、`error` 含「壞掉了」。
- 跳過路徑：內部 `run.skip("非開市日")` → **不拋例外**，DB 內 `status='skipped'`、`error == "非開市日"`。
- `has_successful_run` 對 success 與 skipped 都回 `True`，對 failed 回 `False`，對沒跑過的回 `False`。
- `latest_run` 回傳最新一筆。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed；skipped 只有 TimescaleDB 那一筆
```

### 不要做的事

- 不要在 loader 裡發 HTTP 請求、不要 import `sources/`。
- 不要改 `jobs.py`、`cli.py`、`scheduler.py`（那是 T1-4）。
- 不要加外鍵。

---

## T1-4　Job、CLI、排程：每日盤後自動更新，並修掉 U-3 與 U-5（SPLIT）

> **狀態：SPLIT（2026-09-19，第 4 輪 REQUEST_CHANGES 之後）。**
> 本節保留為「T1-4 的完整設計與契約」，供查閱；**剩下未完成的工作已拆成 T1-4a、T1-4b、T1-4c、T1-4d 四個子任務**（見本文件下方四個獨立小節），
> 請依序執行，一次只做一個子任務。已經做完並通過前四輪審查的部分不要重做。
> 前四輪 REQUEST_CHANGES 的共同原因是「一次要求改太多處，每輪只改了其中一部分」，
> 所以四個子任務各自**只動 1～2 個檔案**、彼此不重疊，驗收指令也各自獨立。

### 目標

把 parser + loader 串成可排程的 job；同時把 M0 的停用保護改成相對比例（U-3），把交易日曆補成「今年 + 明年」並提供由指數反推歷史年度的函式（U-5）。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `etl/twstock_etl/jobs.py` | 修改（大改） |
| `etl/twstock_etl/cli.py` | 修改：新增四個子指令 |
| `etl/twstock_etl/scheduler.py` | 修改（改寫 `build_scheduler`） |
| `etl/twstock_etl/loaders/calendar.py` | 修改：新增 `insert_calendar_if_absent`（見 §2） |
| `etl/tests/test_etl_price_jobs.py` | 新增 |
| `etl/tests/test_etl_loaders.py`、`test_etl_cli.py`、`test_etl_scheduler.py` | 修改：跟著新行為調整 |

**這張表以外的 production 程式不准動**，尤其是 `etl/twstock_etl/loaders/job_log.py`
（T1-3 已審查 DONE，`JobSkipped` 不往外拋是既定契約，見 D-024）與 `etl/twstock_etl/sources/`。
真的覺得非改不可，先停下來回報，由 Architect 改規格，不要自己改實作再回頭改測試斷言。

### 1. `jobs.py`：U-3 停用保護改相對比例

刪掉 `MIN_RECORDS_FOR_DEACTIVATE = 500`，改成：

```python
DEACTIVATE_MIN_RATIO = 0.7   # 本次筆數 / 前次 active 筆數 的下限
DEACTIVATE_MIN_ABSOLUTE = 50 # 資料庫還沒有該市場資料時的絕對下限
```

`refresh_stock_list` 改成單一交易內先比對再寫：

```python
with engine.begin() as conn:
    if deactivate:
        previous = count_active_stocks(conn, market)
        if previous > 0 and len(records) < previous * DEACTIVATE_MIN_RATIO:
            raise SourceFormatError(
                f"{market} 本次解析 {len(records)} 筆，低於前次有效筆數 {previous} 的 "
                f"{DEACTIVATE_MIN_RATIO:.0%}（門檻 {previous * DEACTIVATE_MIN_RATIO:.0f} 筆），拒絕停用缺漏個股"
            )
        if previous == 0 and len(records) < DEACTIVATE_MIN_ABSOLUTE:
            raise SourceFormatError(
                f"{market} 本次解析 {len(records)} 筆，少於初次建庫下限 "
                f"{DEACTIVATE_MIN_ABSOLUTE} 筆，拒絕停用缺漏個股"
            )
    loaded = upsert_stocks(conn, records)
    deactivated = deactivate_missing(conn, market, {r.stock_id for r in records}) if deactivate else 0
```

`deactivate=False`（CLI 預設、fixture 載入）時**完全不檢查**，行為與 M0 相同。

### 2. `jobs.py`：U-5 交易日曆

```python
def refresh_trading_calendar(engine, year, *, payload=None, client=None) -> CalendarLoadResult:
    """（不變）"""


def refresh_calendar_with_next_year(
    engine: Engine, year: int, *, client: httpx.Client | None = None
) -> list[CalendarLoadResult]:
    """刷新 year 與 year+1 的交易日曆。

    year+1 的資料在官方尚未公布時（build_calendar 拋 SourceFormatError）
    記 INFO log 並略過，不視為失敗。回傳成功的結果清單（長度 1 或 2）。
    只下載一次 payload，兩個年度共用。
    """


def rebuild_calendar_from_index(
    engine: Engine, year: int, *, index_id: str = "TAIEX", overwrite: bool = False
) -> CalendarLoadResult:
    """用 index_daily 已回補的指數交易日反推某歷史年度的交易日曆。

    1. dates = index_trade_dates(conn, index_id, year)
    2. len(dates) < 200 → raise SourceFormatError(f"{year} 年 {index_id} 只有 {n} 個交易日，
       不足以推算日曆，請先回補指數")
    3. 產生該年每一天：在 dates 內 → is_open=True、note=None；
       否則 is_open=False、note="未開市（由指數回補推得）"
    4. overwrite=False → 用 ON CONFLICT DO NOTHING（不覆蓋官方來源已寫入的 note）
       overwrite=True  → 用既有的 upsert_calendar
    """
```

`upsert_calendar` 不動；`overwrite=False` 的分支在 `loaders/calendar.py` 另外加一個
`insert_calendar_if_absent(conn, days) -> int`（`on_conflict_do_nothing(index_elements=["trade_date"])`，回傳 `result.rowcount`）。

### 3. `jobs.py`：價格 job

**共同契約（三個價格 job 函式一律照此，見 D-024；第 1～3 輪審查的 Blocker 全部出在這一段沒有寫清楚）**

1. 每個 job 函式回傳自己的 `@dataclass(frozen=True)`，欄位一律包含 `rows: int` 與
   `skip_reason: str | None = None`。`skip_reason is None` 代表這次真的有執行；不是 `None`
   代表被略過，此時 `rows == 0`。**不准回傳裸 `int`。**
2. **`JobSkipped` 不會傳到呼叫端**——這是 T1-3 已定案的 `job_run` 契約
   （`loaders/job_log.py` 不屬於本任務的可改檔案，不准為了讓測試通過而改它）。
   呼叫端（CLI、`scheduler.py`、T1-5 回補）一律看回傳值的 `skip_reason`，
   **任何地方都不准寫 `except JobSkipped`**。
3. 回傳值會用到的區域變數**一律在 `with job_run(...)` 之前給好預設值**，函式結尾只有一個
   `return`，直接把 `run.note` 當成 `skip_reason`：

   ```python
   rows = 0
   skipped_unknown = 0
   with job_run(engine, job_name, target_date=trade_date) as run:
       ...
       rows = upsert_result.written
       skipped_unknown = upsert_result.skipped_unknown
       run.rows = rows
   return PriceJobResult(
       market=market, trade_date=trade_date, rows=rows,
       skipped_unknown=skipped_unknown, skip_reason=run.note,
   )
   ```

   被 skip 時 `job_run` 會把 `run.note` 設成原因、控制流直接跳到 `with` 區塊之後，
   預設值原封不動。**不准**寫成 `if run.note is not None: ... else: 用只有成功分支才賦值的變數`
   ——第 2 輪 Blocker 2 的 `UnboundLocalError` 就是這樣來的。
4. 時間相依的判斷（例如「當月」）一律走可注入的 `now` 參數（見 D-026），不准直接在分支裡呼叫
   `datetime.now(TAIPEI)`，否則測試會隨系統日期改變行為。

```python
@dataclass(frozen=True)
class PriceJobResult:
    """單一交易日的日 K 載入結果。"""

    market: str
    trade_date: date
    rows: int
    skipped_unknown: int
    skip_reason: str | None = None


@dataclass(frozen=True)
class IndexJobResult:
    """單一月份的指數日 K 載入結果。"""

    year: int
    month: int
    rows: int
    skip_reason: str | None = None


@dataclass(frozen=True)
class AdjFactorJobResult:
    """單一區間的除權息還原係數載入結果。"""

    start: date
    end: date
    rows: int
    skip_reason: str | None = None


def is_trading_day(conn: Connection, trade_date: date) -> bool | None:
    """查 trading_calendar；True=開市、False=休市、None=日曆沒有這一天。"""


def load_daily_price(
    engine: Engine,
    market: str,
    trade_date: date,
    *,
    payload: dict | None = None,
    client: httpx.Client | None = None,
    check_calendar: bool = True,
    force: bool = False,
) -> PriceJobResult:
    """抓（或用傳入的）單一交易日行情並寫入 daily_price，全程記 etl_job_log。

    流程：
    1. job_name = "daily_price_twse" / "daily_price_tpex"（market.lower()）
    2. with job_run(engine, job_name, target_date=trade_date) as run:
       a. force=False 且 has_successful_run(...) → run.skip("已完成，略過")
       b. check_calendar=True 且 is_trading_day(...) is False → run.skip("非開市日")
          （is_trading_day 回 None 時**繼續執行**，只記 warning「日曆缺少 <date>」）
       c. payload 為 None → fetch_twse_daily / fetch_tpex_daily
       d. parse → upsert_daily_prices → run.rows = result.written
    3. 依上面共同契約第 3 點回傳 PriceJobResult
       （被 skip 時 rows=0、skipped_unknown=0、skip_reason=run.note）

    Raises:
        ValueError: market 不是 TWSE / TPEx
    """


def load_index_month(
    engine: Engine, year: int, month: int, *, payload: dict | None = None,
    client: httpx.Client | None = None, force: bool = False,
    now: datetime | None = None,
) -> IndexJobResult:
    """抓某年某月的 TAIEX 指數歷史並寫入 index_daily。

    job_name="index_daily_taiex"、target_key=f"{year:04d}-{month:02d}"。
    force=False 且已成功過 → skip("已完成，略過")。
    **當月一律視為未完成，不 skip**：當月的判斷基準是 `now or datetime.now(TAIPEI)`
    （測試用 now 注入固定時間，見 §6）。
    """


def load_adj_factors(
    engine: Engine, start: date, end: date, *, payload: dict | None = None,
    client: httpx.Client | None = None, force: bool = False,
) -> AdjFactorJobResult:
    """抓某區間的除權除息計算結果並寫入 adj_factor。

    job_name="adj_factor_twse"、target_key=f"{start:%Y%m%d}-{end:%Y%m%d}"。
    force=False 且已成功過 → skip("已完成，略過")。
    區間長度超過 31 天 → raise ValueError（官方端點一次只吃一個月），
    這個檢查在進 job_run 之前做，不留 etl_job_log 紀錄。
    """
```

### 3.1 既有 job 也要記 `etl_job_log`（規格早已要求，目前仍未實作）

`etl_job_log` 是 ETL 狀態頁（T1-6 §5.4／§5.5）唯一的資料來源，所以**每個會寫資料庫的 job
函式都要包 `job_run`**（見 D-025）。job 名稱一律用 §4 表格的字串：

| 函式 | `job_name` | `target_date` | `target_key` |
| --- | --- | --- | --- |
| `refresh_stock_list` | `stock_list_twse` / `stock_list_tpex`（`market.lower()`） | NULL | `market` |
| `refresh_trading_calendar` | `trading_calendar` | NULL | `f"{year:04d}"` |
| `rebuild_calendar_from_index` | `calendar_from_index` | NULL | `f"{year:04d}"` |

- **簽名與回傳值都不變**，在函式內部包一層即可；M0／T1-3 既有測試對回傳值與例外的斷言必須仍然成立
  （`refresh_stock_list` 的停用保護仍然 raise `SourceFormatError`，由 `job_run` 記 `failed` 後重拋）。
- 這三個 job **不做 `has_successful_run` 去重、也不會 skip**（日曆與個股清單每天都要重刷），
  所以 `run.note` 恆為 `None`，可以直接回傳既有的 result 物件，不必加 `skip_reason` 欄位。
- `refresh_calendar_with_next_year` 本身**不**包 `job_run`：它負責「下載一次 payload、
  解析一次 holidays」，再對 `year` 與 `year + 1` 各呼叫一次寫入路徑，讓兩個年度各留一列
  `trading_calendar` 紀錄。`year + 1` 官方尚未公布時，`build_calendar` 會拋 `SourceFormatError`
  ——**這個判斷必須在進入 `job_run` 之前完成**，只記 INFO log 並略過，
  **不可以留下 `status='failed'` 的紀錄**（否則 ETL 狀態頁的「近 7 天失敗次數」每天 +1，
  又是一次「正常路徑被記成錯誤」）。建議把「寫入單一年度」抽成模組私有函式：

  ```python
  def _write_calendar_year(engine: Engine, year: int, days: Sequence[CalendarDay]) -> CalendarLoadResult:
      """把已經 build 好的某年日曆寫入 trading_calendar，並記一列 etl_job_log。

      job_name="trading_calendar"、target_key=f"{year:04d}"、run.rows = len(days)。
      此 job 不會 skip，直接回傳 CalendarLoadResult。
      """
  ```

  `refresh_trading_calendar` 與 `refresh_calendar_with_next_year` 都改成「fetch → parse →
  build_calendar → `_write_calendar_year`」，寫入與記錄只有一份實作。

### 4. `cli.py` 新增子指令

| 子指令 | 參數 | stdout（成功時最後一行） |
| --- | --- | --- |
| `load-price` | `--market TWSE\|TPEx`（必填）、`--date YYYY-MM-DD`（預設台北時間今天）、`--file PATH`、`--force`、`--no-calendar-check` | `loaded market=TWSE date=2026-09-18 rows=5 skipped_unknown=1` |
| `load-index` | `--year`（預設今年）、`--month`（預設本月）、`--file PATH`、`--force` | `loaded index=TAIEX month=2026-09 rows=3` |
| `load-exright` | `--from YYYY-MM-DD`、`--to YYYY-MM-DD`（預設：最近 7 天，含今天）、`--file PATH`、`--force` | `loaded exright from=2026-09-12 to=2026-09-18 rows=2` |
| `rebuild-calendar` | `--year`（必填）、`--overwrite` | `rebuilt year=2025 days=365 open=246 closed=119` |

- `--file` 一律讀 UTF-8 JSON 後當成 `payload` 傳進 job（不發 HTTP）。
- 被 skip（`result.skip_reason is not None`）時 exit code 仍是 0，stdout 改印下列對應的一行
  （`loaded …` 那行就不印了）；判斷一律看回傳值，**不准 `except JobSkipped`**：

  | 子指令 | 被 skip 時的 stdout |
  | --- | --- |
  | `load-price` | `skipped market=TWSE date=2026-09-20 reason=非開市日` |
  | `load-index` | `skipped index=TAIEX month=2026-09 reason=已完成，略過` |
  | `load-exright` | `skipped exright from=2026-09-01 to=2026-09-30 reason=已完成，略過` |

  （`load-index`／`load-exright` 的 skip 行要和各自的 `loaded …` 行用同一組欄位名，
  只是把 `loaded` 換成 `skipped`、把 `rows=…` 換成 `reason=…`。`rebuild-calendar` 不會 skip。）
- 錯誤處理沿用既有 `try/except`（`SourceFormatError`、`httpx.HTTPError`、`RuntimeError`、`FileNotFoundError`、`SQLAlchemyError`），
  印 `error: …` 到 stderr、回 1。

### 5. `scheduler.py` 改寫

`build_scheduler(engine)` 註冊下列 job（全部 `timezone=TAIPEI`、`coalesce=True`、`max_instances=1`、`misfire_grace_time=3600`）：

| id | trigger | 動作 |
| --- | --- | --- |
| `refresh_trading_calendar` | `CronTrigger(hour=7, minute=30)` | `refresh_calendar_with_next_year(engine, 今年)` |
| `refresh_stock_list` | `CronTrigger(hour=8, minute=0)` | 既有的 `run_stock_list_job` |
| `daily_price_twse` | `CronTrigger(hour="15,17,19", minute=35)` | `load_daily_price(engine, "TWSE", 今天)` |
| `daily_price_tpex` | `CronTrigger(hour="15,17,19", minute=45)` | `load_daily_price(engine, "TPEx", 今天)` |
| `index_daily_taiex` | `CronTrigger(hour="15,17,19", minute=55)` | `load_index_month(engine, 今年, 本月, force=True)` |
| `adj_factor_twse` | `CronTrigger(hour=16, minute=10)` | `load_adj_factors(engine, 今天-7天, 今天)` |

- **重試機制就是「同一天排三次」**：15:35 抓失敗時，17:35 與 19:35 會再跑；已成功的日期靠
  `has_successful_run` 直接 `skip`，不會重複抓（見 D-022）。
- 每個 wrapper 函式（`run_daily_price_job(engine, market)` 等）內部 `try/except Exception: logger.exception(...)`，
  單一 job 失敗不可中斷排程器。
- **wrapper 一律透過回傳的結果物件取值，不准把結果物件直接丟給 `%d`**（第 3 輪 Blocker 4：
  `logger.info("… %d 筆", result)` 會在 `logging` 內部拋 `TypeError`，被 `logging` 自己吞掉、
  在 stderr 印一段 `--- Logging error ---` traceback，外層 `except Exception` 根本接不到）。
  四個價格／指數／除權息 wrapper 一律用同一個模組私有 helper 記錄結果，
  **「略過」要記成 INFO 的略過、不可以印成「成功載入 0 筆」**：

  ```python
  def _log_job_outcome(what: str, result) -> None:
      """統一記錄 job 結果：被略過記「略過」，實際執行記筆數。

      result 需有 rows: int 與 skip_reason: str | None（見 §3 共同契約）。
      """
      if result.skip_reason is not None:
          logger.info("%s 略過：%s", what, result.skip_reason)
      else:
          logger.info("%s 成功載入 %d 筆", what, result.rows)
  ```

  呼叫範例：`_log_job_outcome(f"{today} {market} 日成交", load_daily_price(engine, market, today))`、
  `_log_job_outcome(f"{year:04d}-{month:02d} TAIEX 指數", load_index_month(engine, year, month, force=True))`、
  `_log_job_outcome(f"{start} 至 {end} 除權除息", load_adj_factors(engine, start, end))`。
- wrapper 內不准再寫區域 `import`（`timedelta` 等一律併到 `scheduler.py` 頂層 import）。
- 只有 `refresh_trading_calendar` 與 `refresh_stock_list` 保留 `next_run_time=datetime.now(TAIPEI)`（啟動即跑一次）；
  價格 job **不要**在啟動時立刻跑（避免容器重啟就打來源）。

### 6. 測試

> 本小節是 T1-4 原始範圍的測試清單，供查閱。**實際要補的測試以 T1-4a～T1-4d 各子任務小節為準**，兩邊有出入時以子任務小節為準。

`test_etl_price_jobs.py`（需要 DB）：
- 先插 `stock`（1101、2317、2330、2834、0050）與 `trading_calendar`（2026-09-18 開市、2026-09-19 休市）。
- `load_daily_price(engine, "TWSE", date(2026,9,18), payload=fixture)` → `result.rows == 4`（2882 不在 stock 表，2834 無成交）。
- 再跑一次（`force=False`）→ `result.rows == 0`、`result.skip_reason == "已完成，略過"`，
  且 `etl_job_log` 多出一列 `status='skipped'`、`error='已完成，略過'`。
- `force=True` 再跑 → `result.rows == 4`、`result.skip_reason is None`。
- `load_daily_price(engine, "TWSE", date(2026,9,19), payload=fixture)` → skip，`etl_job_log` 記 `非開市日`。
- `load_index_month(engine, 2026, 9, payload=fixture)` → `result.rows == 3`。
- **不依賴系統當前日期的 skip 測試**（第 2 輪 Blocker 2 的核心情境，目前的
  `test_load_index_month_skip_when_done` 用「跑測試當下的當月」，永遠走不到 skip 分支）：
  同一個 `(2026, 9)` 連跑兩次，第二次傳 `now=datetime(2027, 1, 15, tzinfo=TAIPEI)`
  → `result.rows == 0`、`result.skip_reason == "已完成，略過"`，且**不拋例外**。
- 當月不 skip：同一個 `(2026, 9)` 連跑兩次、第二次傳 `now=datetime(2026, 9, 30, tzinfo=TAIPEI)`
  → `result.rows == 3`、`result.skip_reason is None`。
- `load_adj_factors(engine, date(2026,9,1), date(2026,9,30), payload=fixture)` → `result.rows == 2`；
  再跑一次（`force=False`）→ `result.rows == 0`、`result.skip_reason == "已完成，略過"`且不拋例外；
  `force=True` 再跑 → `result.rows == 2`。
- `load_adj_factors(..., start=date(2026,1,1), end=date(2026,12,31))` → `pytest.raises(ValueError)`。
- `rebuild_calendar_from_index(engine, 2026)` → `pytest.raises(SourceFormatError)`（只有 3 天指數資料）。
- 停用保護：插 100 筆 active 個股 → `refresh_stock_list(engine, "TWSE", html=fixture, deactivate=True)`
  （fixture 只有 9 筆，9 < 70）→ `pytest.raises(SourceFormatError)`，訊息含 `70%`；且 DB 內 100 筆仍 active。
- `deactivate=False` 時同樣的呼叫要成功。
- §3.1 的 `etl_job_log` 紀錄：`refresh_stock_list(engine, "TWSE", html=fixture)` 後，
  `etl_job_log` 有一列 `job_name='stock_list_twse'`、`target_key='TWSE'`、`status='success'`；
  `refresh_trading_calendar(engine, 2026, payload=fixture)` 後有一列
  `job_name='trading_calendar'`、`target_key='2026'`、`status='success'`；
  停用保護觸發的那次 `refresh_stock_list` 則留下一列 `status='failed'`。

`test_etl_cli.py` 追加：
- `main(["load-price", "--market", "TWSE", "--file", str(fixture), "--date", "2026-09-18", "--no-calendar-check"])`
  回 0，`capsys` 抓到的 stdout 含 `rows=4`；同一個指令再跑一次 → 回 0、stdout 含
  `skipped market=TWSE date=2026-09-18 reason=已完成，略過`。
- `load-index`、`load-exright` 各一個成功案例；`load-exright` 再跑一次 → 回 0、stdout 含
  `skipped exright from=… to=… reason=已完成，略過`（斷言整行格式，不要只斷言 `"skipped" in out`）。

`test_etl_scheduler.py` 追加（需要 DB，`monkeypatch` 掉
`twstock_etl.jobs.fetch_taiex_month` / `fetch_exright` / `fetch_twse_daily` 改用 fixture payload，不打網路）：
- **四個 wrapper 的「成功」路徑各一個測試**（`run_daily_price_job`、`run_index_month_job`、
  `run_adj_factors_job`、`run_trading_calendar_job`）：用 `caplog.at_level(logging.INFO)` 斷言
  該 wrapper 的成功訊息有出現（前三個是 `_log_job_outcome` 的「成功載入 N 筆」、
  最後一個是既有的「成功刷新 N 個年份的交易日曆」），且 `caplog.text` **不含**
  `Logging error`、`TypeError`、`Traceback`（第 3 輪 Blocker 4 就是只有「成功」路徑會炸，
  而且炸在 `logging` 內部、不會讓測試自然失敗，所以一定要對 log 內容下斷言）。
- **`run_daily_price_job` 的「略過」路徑**：同一天連呼叫兩次，第二次的 log 含「略過」與
  `已完成，略過`，且 `caplog` 內**沒有任何 ERROR 等級的紀錄**（第 1 輪 Blocker 1 的回歸測試）。
- 既有的 `test_scheduler_jobs`（job id 集合）、`test_scheduler_job_triggers`（trigger 與時區）維持。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed

cd /home/claude/TwStock && export DATABASE_URL=$(scripts/pg_temp.sh reset) && \
  .venv/bin/alembic -c db/alembic.ini upgrade head >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TPEx --file etl/tests/fixtures/isin_tpex_strmode4.html && \
  .venv/bin/python -m twstock_etl.cli load-calendar --year 2026 --file etl/tests/fixtures/twse_holiday_schedule_2026.json && \
  .venv/bin/python -m twstock_etl.cli load-price --market TWSE --date 2026-09-18 --file etl/tests/fixtures/TWSE_price_20260918.json && \
  .venv/bin/python -m twstock_etl.cli load-price --market TPEx --date 2026-09-18 --file etl/tests/fixtures/TPEx_price_20260918.json && \
  .venv/bin/python -m twstock_etl.cli load-index --year 2026 --month 9 --file etl/tests/fixtures/TAIEX_index_202609.json && \
  .venv/bin/python -m twstock_etl.cli load-exright --from 2026-09-01 --to 2026-09-30 --file etl/tests/fixtures/exright_20260901_20260930.json
# 預期（最後四行）：
# loaded market=TWSE date=2026-09-18 rows=4 skipped_unknown=1
# loaded market=TPEx date=2026-09-18 rows=3 skipped_unknown=1
# loaded index=TAIEX month=2026-09 rows=3
# loaded exright from=2026-09-01 to=2026-09-30 rows=2

cd /home/claude/TwStock && .venv/bin/python -m twstock_etl.cli load-price --market TWSE --date 2026-09-18 --file etl/tests/fixtures/TWSE_price_20260918.json && \
  .venv/bin/python -m twstock_etl.cli load-exright --from 2026-09-01 --to 2026-09-30 --file etl/tests/fixtures/exright_20260901_20260930.json && \
  .venv/bin/python -m twstock_etl.cli load-index --year 2026 --month 9 --file etl/tests/fixtures/TAIEX_index_202609.json
# 預期（三行，exit 0）：
# skipped market=TWSE date=2026-09-18 reason=已完成，略過
# skipped exright from=2026-09-01 to=2026-09-30 reason=已完成，略過
# loaded index=TAIEX month=2026-09 rows=3   ← 當月一律重跑，不 skip

# 每個 job 都有 etl_job_log 紀錄（§3.1）
cd /home/claude/TwStock && /usr/lib/postgresql/16/bin/psql "${DATABASE_URL/postgresql+psycopg/postgresql}" \
  -c "SELECT job_name, target_key, status, count(*) FROM etl_job_log GROUP BY 1,2,3 ORDER BY 1,2,3"
# 預期：job_name 至少要出現 stock_list_twse、stock_list_tpex、trading_calendar、
#       daily_price_twse、daily_price_tpex、index_daily_taiex、adj_factor_twse 七種，
#       且沒有任何 status='failed' 的列
```

### 不要做的事

- 不要在這個任務寫回補腳本（T1-5）、API（T1-6）、前端（T1-7）。
- 不要把排程時間寫成 UTC——一律 `Asia/Taipei`。
- 不要引入 APScheduler 的 job store／持久化（`etl_job_log` 就是我們的紀錄）。
- 不要動 `sources/` 的程式。

### 修正指引（Architect，2026-09-19，第 3 輪 REQUEST_CHANGES 之後）

`docs/reviews/T1-4.md` 連續三輪的 Blocker 其實是**同一個根因**：規格只替 `load_daily_price`
訂了結果物件，另外兩個 job 寫「回傳筆數」，也沒訂 skip 要怎麼傳給呼叫端、scheduler wrapper
要怎麼記 log、哪些呼叫端必須跟著改——所以每修一處就冒出下一處。規格側的洞已經在上面補好
（§3 共同契約、§3.1 `etl_job_log` 包裝、§4 skip 輸出、§5 `_log_job_outcome`、§6 測試，
以及 `docs/decisions.md` 的 D-024／D-025／D-026）。**這一輪請只做下面這幾件事，不要重構其他東西。**

#### 1.（Blocker 4）`etl/twstock_etl/scheduler.py`：wrapper 沒跟著 dataclass 回傳型別一起改

- 現況：`run_index_month_job` 的 `rows = load_index_month(...)` + `logger.info("… %d 筆", …, rows)`，
  `run_adj_factors_job` 的 `rows = load_adj_factors(...)` + `logger.info("… %d 筆", …, rows)`。
  `rows` 其實是 `IndexJobResult` / `AdjFactorJobResult`，`%d` 會在 `logging` 內部拋
  `TypeError`，被 `logging` 自己吞掉、在 stderr 印 `--- Logging error ---` 加整段 traceback；
  外層 `except Exception` 接不到，所以測試也不會紅。**每天排程真的成功那一次都會發生。**
- 做法：照 §5 新增模組私有 helper `_log_job_outcome(what, result)`，把三個價格／指數／
  除權息 wrapper（`run_daily_price_job`、`run_index_month_job`、`run_adj_factors_job`）
  的成功路徑一律改成 `result = load_xxx(...)` + `_log_job_outcome(...)`。
  `run_daily_price_job` 雖然已經用 `result.rows` 不會炸，但被 skip 時會印成
  「成功載入 0 筆」，一樣要改成走 helper 印「略過：已完成，略過」。
  `run_stock_list_job` 與 `run_trading_calendar_job` 回傳的不是這組 dataclass，維持現有寫法。
- 順手：把 `run_adj_factors_job` 內的 `from datetime import timedelta` 移到檔案頂層
  （`from datetime import datetime, timedelta`）。

#### 2.（規格早已要求、三輪都沒做）`etl/twstock_etl/jobs.py`：既有 job 補 `etl_job_log`

- 依 §3.1 把 `refresh_stock_list`、`refresh_trading_calendar`、`rebuild_calendar_from_index`
  各包一層 `job_run`，job 名稱與 `target_key` 照 §3.1 表格；簽名與回傳值不變。
- `refresh_calendar_with_next_year` 依 §3.1 改成「下載／解析一次 → 對兩個年度各
  `build_calendar` → `_write_calendar_year`」，`year + 1` 尚未公布時在**進 `job_run` 之前**
  就攔下 `SourceFormatError`，只記 INFO，不可以留 `status='failed'` 的列。
- 這件事不是可有可無的補強：T1-6 §5.4／§5.5 的 ETL 狀態頁完全靠 `etl_job_log`，
  現在個股清單與日曆兩個每天都在跑的 job 在狀態頁上是完全空白的。

#### 3.（第 3 輪 Minor）`etl/twstock_etl/jobs.py`：三個價格 job 改用 §3 的單一 `return` 寫法

- 目前 `load_daily_price` / `load_index_month` / `load_adj_factors` 結尾都是
  `if run.note is not None: return …(rows=0) else: return …(rows=run.rows)`。
  功能正確，但正是這個寫法讓第 2 輪漏改兩個函式就炸 `UnboundLocalError`。
- 改成 §3 共同契約第 3 點的寫法：`rows = 0`（`skipped_unknown = 0`、`result = None` 等）
  先在 `with` 之前給預設值，結尾只留一個 `return …(rows=rows, …, skip_reason=run.note)`。
- `load_index_month` 依 §3 加上 `now: datetime | None = None`，當月判斷改成
  `ref = now or datetime.now(TAIPEI)`。

#### 4.（第 3 輪 Minor）CLI skip 輸出格式對齊 §4 表格

- `etl/twstock_etl/cli.py::_cmd_load_index` 目前印 `skipped month=2026-09 reason=…`，
  改成 `skipped index=TAIEX month=2026-09 reason=…`。
- `_cmd_load_exright` 目前印 `skipped from=… to=… reason=…`，
  改成 `skipped exright from=… to=… reason=…`。
- 兩處判斷維持看 `result.skip_reason`，不要引入 `JobSkipped`。

#### 5. 測試：照 §6 補齊

重點是 `etl/tests/test_etl_scheduler.py` 的四個 wrapper 測試（成功路徑 + `run_daily_price_job`
的略過路徑），以及 `test_etl_price_jobs.py` 用 `now` 注入、不依賴系統當前日期的
`load_index_month` skip／不 skip 兩個測試。現有
`test_load_index_month_skip_when_done` 請改寫成注入 `now=datetime(2027, 1, 15, tzinfo=TAIPEI)`
的版本（目前這個測試名不副實：2026-09 就是跑測試當下的當月，永遠走不到 skip）。

#### 6. 仍然不准做的事

- 不准再動 `etl/twstock_etl/loaders/job_log.py`（`JobSkipped` 不往外拋是 T1-3 定案的契約）。
- 不准為了讓測試通過而反轉既有測試的斷言方向；測試與規格衝突時先回報，不要自己改規格。
- 不准在任何地方寫 `except JobSkipped`。
- 不准改 `sources/`、`loaders/price.py` 的解析邏輯。
- 回報 `changed_files` 要與 `git status` 一致（第 1 輪的回報漏了 7 個檔案）。

> **上面這份「修正指引」第 1～5 項已於 2026-09-19 第 4 輪之後全數改寫成 T1-4a～T1-4d 四個子任務**（第 1 項 → T1-4c、第 2 項 → T1-4d、第 3 項 → T1-4a、第 4 項 → T1-4b、第 5 項 → 分散在四個子任務內）。
> 請不要再照這份指引一次做完，改看下方四個子任務小節，一次做一個、一個一個驗收。
> 第 6 項「仍然不准做的事」**繼續適用於每一個子任務**。

---

## T1-4a　`jobs.py`：三個價格 job 改成單一 `return`，`load_index_month` 加 `now` 注入

依賴：T1-4（BLOCKED，已拆分）。這是 T1-4 拆分後的第 1 個子任務，先做這個。

### 範圍（只准動這兩個檔案）

| 路徑 | 動作 |
| --- | --- |
| `etl/twstock_etl/jobs.py` | 修改，**只准動 `load_daily_price`、`load_index_month`、`load_adj_factors` 這三個函式的函式本體** |
| `etl/tests/test_etl_price_jobs.py` | 修改：改寫 1 個既有測試、新增 1 個測試、補 2 行 import |

`jobs.py` 裡的 `refresh_stock_list`、`refresh_trading_calendar`、`refresh_calendar_with_next_year`、
`rebuild_calendar_from_index`、`is_trading_day` 與檔案頂部的 import **這個子任務一律不准動**（留給 T1-4d）。
`cli.py`、`scheduler.py`、`loaders/`、`sources/` 也不准動（各有自己的子任務）。

### 1. `load_daily_price`：整個函式換成下面這段

現況（`etl/twstock_etl/jobs.py`）結尾是 `if run.note is not None: return PriceJobResult(...) else: return PriceJobResult(...)`，
依 §3 共同契約第 3 點改成「變數先給預設值、結尾只有一個 `return`」。把 `def load_daily_price(` 到該函式最後一行
整段換成：

```python
def load_daily_price(
    engine: Engine,
    market: str,
    trade_date: date,
    *,
    payload: dict | None = None,
    client: httpx.Client | None = None,
    check_calendar: bool = True,
    force: bool = False,
) -> PriceJobResult:
    """抓（或用傳入的）單一交易日行情並寫入 daily_price，全程記 etl_job_log。

    Args:
        engine: SQLAlchemy Engine
        market: 市場別（TWSE、TPEx）
        trade_date: 交易日
        payload: 若提供則用此 JSON payload，否則下載
        client: httpx.Client；為 None 時建立新的
        check_calendar: 是否檢查交易日曆
        force: 是否強制重抓

    Returns:
        PriceJobResult；被略過時 rows=0、skipped_unknown=0、skip_reason 為略過原因

    Raises:
        ValueError: market 不是 TWSE / TPEx
    """
    if market not in ("TWSE", "TPEx"):
        raise ValueError(f"市場別錯誤：{market}")

    job_name = f"daily_price_{market.lower()}"
    rows = 0
    skipped_unknown = 0

    with job_run(engine, job_name, target_date=trade_date) as run:
        with engine.begin() as conn:
            # 檢查是否已完成
            if not force and has_successful_run(
                conn, job_name, target_date=trade_date
            ):
                run.skip("已完成，略過")

            # 檢查交易日曆
            if check_calendar:
                is_open = is_trading_day(conn, trade_date)
                if is_open is False:
                    run.skip("非開市日")
                elif is_open is None:
                    logger.warning("日曆缺少 %s", trade_date)

        # 抓或讀取資料
        if payload is None:
            if market == "TWSE":
                payload = fetch_twse_daily(trade_date, client)
            else:
                payload = fetch_tpex_daily(trade_date, client)

        # 解析
        if market == "TWSE":
            records = parse_twse_daily(payload, trade_date)
        else:
            records = parse_tpex_daily(payload, trade_date)

        # 寫入
        with engine.begin() as conn:
            upsert_result = upsert_daily_prices(conn, records)
        rows = upsert_result.written
        skipped_unknown = upsert_result.skipped_unknown
        run.rows = rows

    return PriceJobResult(
        market=market,
        trade_date=trade_date,
        rows=rows,
        skipped_unknown=skipped_unknown,
        skip_reason=run.note,
    )
```

### 2. `load_index_month`：整個函式換成下面這段（新增 `now` 參數）

```python
def load_index_month(
    engine: Engine,
    year: int,
    month: int,
    *,
    payload: dict | None = None,
    client: httpx.Client | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> IndexJobResult:
    """抓某年某月的 TAIEX 指數歷史並寫入 index_daily，回傳結果。

    當月（now 或台北時間今天所在的月）一律視為未完成，不 skip。

    Args:
        engine: SQLAlchemy Engine
        year: 年份
        month: 月份
        payload: 若提供則用此 JSON payload，否則下載
        client: httpx.Client；為 None 時建立新的
        force: 是否強制重抓
        now: 判斷「當月」的基準時間；為 None 時用 datetime.now(TAIPEI)（見 D-026）

    Returns:
        IndexJobResult；被略過時 rows=0、skip_reason 為略過原因
    """
    target_key = f"{year:04d}-{month:02d}"
    job_name = "index_daily_taiex"
    rows = 0

    with job_run(engine, job_name, target_key=target_key) as run:
        # 檢查是否為當月（基準時間可注入，不直接在分支裡呼叫 datetime.now）
        ref = now or datetime.now(TAIPEI)
        is_current_month = ref.year == year and ref.month == month

        # 檢查是否已完成（當月一律跳過此檢查）
        with engine.begin() as conn:
            if (
                not force
                and not is_current_month
                and has_successful_run(conn, job_name, target_key=target_key)
            ):
                run.skip("已完成，略過")

        # 抓或讀取資料
        if payload is None:
            payload = fetch_taiex_month(year, month, client)

        # 解析
        records = parse_taiex_month(payload, year, month)

        # 寫入
        with engine.begin() as conn:
            rows = upsert_index_daily(conn, records)
        run.rows = rows

    return IndexJobResult(year=year, month=month, rows=rows, skip_reason=run.note)
```

### 3. `load_adj_factors`：整個函式換成下面這段

```python
def load_adj_factors(
    engine: Engine,
    start: date,
    end: date,
    *,
    payload: dict | None = None,
    client: httpx.Client | None = None,
    force: bool = False,
) -> AdjFactorJobResult:
    """抓某區間的除權除息計算結果並寫入 adj_factor，回傳結果。

    Args:
        engine: SQLAlchemy Engine
        start: 起始日期（含）
        end: 結束日期（含）
        payload: 若提供則用此 JSON payload，否則下載
        client: httpx.Client；為 None 時建立新的
        force: 是否強制重抓

    Returns:
        AdjFactorJobResult；被略過時 rows=0、skip_reason 為略過原因

    Raises:
        ValueError: 區間長度超過 31 天
    """
    delta = (end - start).days
    if delta > 31:
        raise ValueError("區間長度不可超過 31 天（官方端點限制）")

    target_key = f"{start:%Y%m%d}-{end:%Y%m%d}"
    job_name = "adj_factor_twse"
    rows = 0

    with job_run(engine, job_name, target_key=target_key) as run:
        with engine.begin() as conn:
            if not force and has_successful_run(conn, job_name, target_key=target_key):
                run.skip("已完成，略過")

        # 抓或讀取資料
        if payload is None:
            payload = fetch_exright(start, end, client)

        # 解析
        records = parse_exright(payload)

        # 寫入
        with engine.begin() as conn:
            upsert_result = upsert_adj_factors(conn, records)
        rows = upsert_result.written
        run.rows = rows

    return AdjFactorJobResult(start=start, end=end, rows=rows, skip_reason=run.note)
```

三個函式改完後，`jobs.py` 全檔**不准**再出現 `if run.note is not None`。

### 4. 測試（`etl/tests/test_etl_price_jobs.py`）

**4.1 補 import。** 把第 4 行 `from datetime import date` 改成 `from datetime import date, datetime`，
並在 `from twstock_etl.jobs import (` 的名單裡加入 `TAIPEI`（名單改成
`TAIPEI, load_adj_factors, load_daily_price, load_index_month, rebuild_calendar_from_index`）。

**4.2 改寫既有的 `test_load_index_month_skip_when_done`**（目前用「跑測試當下的當月」，永遠走不到 skip 分支，
名不副實）。整個函式換成：

```python
def test_load_index_month_skip_when_done(setup_db):
    """非當月且已完成時要 skip，且不拋例外（不依賴系統當前日期）。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/TAIEX_index_202609.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    # 第一次：用注入的「當月」時間，一定會實際執行
    first = load_index_month(
        engine, 2026, 9, payload=payload, now=datetime(2026, 9, 30, tzinfo=TAIPEI)
    )
    assert first.rows == 3
    assert first.skip_reason is None

    # 第二次：注入非當月的時間 → 應該 skip，回傳 rows=0 而不是拋 UnboundLocalError
    second = load_index_month(
        engine, 2026, 9, payload=payload, now=datetime(2027, 1, 15, tzinfo=TAIPEI)
    )
    assert second.rows == 0
    assert second.skip_reason == "已完成，略過"
```

**4.3 新增測試 `test_load_index_month_current_month_not_skipped`**，放在
`test_load_index_month_skip_when_done` 後面：

```python
def test_load_index_month_current_month_not_skipped(setup_db):
    """當月一律重跑，不 skip（不依賴系統當前日期）。"""
    engine = setup_db
    fixture_path = Path("etl/tests/fixtures/TAIEX_index_202609.json")

    with open(fixture_path) as f:
        payload = json.load(f)

    ref = datetime(2026, 9, 30, tzinfo=TAIPEI)
    first = load_index_month(engine, 2026, 9, payload=payload, now=ref)
    assert first.rows == 3

    second = load_index_month(engine, 2026, 9, payload=payload, now=ref)
    assert second.rows == 3
    assert second.skip_reason is None
```

其餘測試不准動。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) \
  .venv/bin/python -m pytest etl/tests/test_etl_price_jobs.py -q
# 預期：輸出含 "14 passed"（13 個既有 + 本子任務新增 1 個），0 failed

cd /home/claude/TwStock && grep -c "if run.note is not None" etl/twstock_etl/jobs.py
# 預期：0

cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) \
  .venv/bin/python -m pytest -rs -q
# 預期：全部 passed、0 failed；skipped 只有「此 PostgreSQL 未安裝 TimescaleDB…」那一筆
```

### 不要做的事

- 不准動 `jobs.py` 的其他函式、頂部 import、三個 dataclass 定義（它們已經正確）。
- 不准動 `cli.py`、`scheduler.py`、`loaders/job_log.py`、`sources/`。
- 不准寫 `except JobSkipped`。

---

## T1-4b　`cli.py`：`load-index`／`load-exright` 的 skip 輸出對齊 §4 表格

依賴：T1-4a。

### 範圍（只准動這兩個檔案）

| 路徑 | 動作 |
| --- | --- |
| `etl/twstock_etl/cli.py` | 修改：**只動 `_cmd_load_index` 與 `_cmd_load_exright` 各一行 `print`** |
| `etl/tests/test_etl_cli.py` | 修改：改寫 1 個既有測試的斷言、新增 1 個測試 |

### 1. `_cmd_load_index`（`etl/twstock_etl/cli.py`）

把這一行：

```python
        print(f"skipped month={year:04d}-{month:02d} reason={result.skip_reason}")
```

改成：

```python
        print(
            f"skipped index=TAIEX month={year:04d}-{month:02d} "
            f"reason={result.skip_reason}"
        )
```

### 2. `_cmd_load_exright`（`etl/twstock_etl/cli.py`）

把這一行：

```python
        print(f"skipped from={start} to={end} reason={result.skip_reason}")
```

改成：

```python
        print(f"skipped exright from={start} to={end} reason={result.skip_reason}")
```

`cli.py` 其餘部分（argparse、`_cmd_load_price`、錯誤處理）一律不准動。

### 3. 測試（`etl/tests/test_etl_cli.py`）

**3.1 改寫 `test_load_exright_cli_skip` 的最後兩行斷言**（規格要求斷言整行，不要只斷言
`"skipped" in out`）。把：

```python
    assert "skipped" in out2
    assert "已完成，略過" in out2
```

換成：

```python
    assert (
        "skipped exright from=2026-09-01 to=2026-09-30 reason=已完成，略過" in out2
    )
```

**3.2 新增測試 `test_load_index_cli_skip`**，放在 `test_load_index_cli_force` 之後。
`load-index` 的 skip 只有「非當月 + 已成功過」才會發生，而 CLI 沒有 `now` 注入，
所以先直接往 `etl_job_log` 塞一筆遠古月份的成功紀錄，再跑 CLI：

```python
def test_load_index_cli_skip(clean_db, monkeypatch, capsys):
    """測試 load-index CLI 被 skip 時的輸出格式。"""
    import os
    from twstock_db.tables import etl_job_log

    database_url = os.environ.get("TWSTOCK_TEST_DATABASE_URL")
    if database_url:
        monkeypatch.setenv("DATABASE_URL", database_url)
        get_engine.cache_clear()

    # 先塞一筆「2000-01 已成功」的紀錄（遠古月份，不會是當月）
    with clean_db.begin() as conn:
        conn.execute(
            etl_job_log.insert().values(
                job_name="index_daily_taiex",
                target_key="2000-01",
                status="success",
                rows=0,
            )
        )

    result = main([
        "load-index",
        "--year", "2000",
        "--month", "1",
        "--file", _fixture_path("TAIEX_index_202609.json"),
    ])

    assert result == 0
    out, err = capsys.readouterr()
    assert "skipped index=TAIEX month=2000-01 reason=已完成，略過" in out

    get_engine.cache_clear()
```

（此測試會在 `parse_taiex_month` 之前就 skip，所以 fixture 的年月不符不影響。）

其餘測試不准動。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) \
  .venv/bin/python -m pytest etl/tests/test_etl_cli.py -q
# 預期：輸出含 "13 passed"（12 個既有 + 本子任務新增 1 個），0 failed

cd /home/claude/TwStock && export DATABASE_URL=$(scripts/pg_temp.sh reset) && \
  .venv/bin/alembic -c db/alembic.ini upgrade head >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-exright --from 2026-09-01 --to 2026-09-30 --file etl/tests/fixtures/exright_20260901_20260930.json && \
  .venv/bin/python -m twstock_etl.cli load-exright --from 2026-09-01 --to 2026-09-30 --file etl/tests/fixtures/exright_20260901_20260930.json
# 預期（兩行，exit 0）：
# loaded exright from=2026-09-01 to=2026-09-30 rows=2
# skipped exright from=2026-09-01 to=2026-09-30 reason=已完成，略過

cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) \
  .venv/bin/python -m pytest -rs -q
# 預期：全部 passed、0 failed
```

### 不要做的事

- 不准動 `jobs.py`、`scheduler.py`。
- 不准寫 `except JobSkipped`。
- 不准改 `_cmd_load_price` 的輸出（它已經對齊規格）。

---

## T1-4c　`scheduler.py`：`_log_job_outcome` helper 與四個 wrapper 的 log 測試

依賴：T1-4a。

### 範圍（只准動這兩個檔案）

| 路徑 | 動作 |
| --- | --- |
| `etl/twstock_etl/scheduler.py` | 修改：頂層 import 加 `timedelta`、新增 `_log_job_outcome`、改寫 `run_daily_price_job`／`run_index_month_job`／`run_adj_factors_job` |
| `etl/tests/test_etl_scheduler.py` | 修改：改寫 2 個既有測試的斷言、新增 3 個測試 |

`run_stock_list_job` 與 `run_trading_calendar_job` 的函式本體、`build_scheduler` 一律不准動
（cron 時間、`timezone`、`coalesce`／`max_instances`／`misfire_grace_time`、`next_run_time` 都已通過審查）。

### 1. 頂層 import（`etl/twstock_etl/scheduler.py`）

把第 4 行：

```python
from datetime import datetime
```

改成：

```python
from datetime import datetime, timedelta
```

### 2. 新增模組私有 helper

在 `TAIPEI = ZoneInfo("Asia/Taipei")` 之後、`def run_stock_list_job` 之前插入：

```python
def _log_job_outcome(what: str, result) -> None:
    """統一記錄 job 結果：被略過記「略過」，實際執行記筆數。

    result 需有 rows: int 與 skip_reason: str | None（見規格 §3 共同契約、D-024）。

    Args:
        what: 這次 job 的描述，例如「2026-09-18 TWSE 日成交」
        result: PriceJobResult / IndexJobResult / AdjFactorJobResult
    """
    if result.skip_reason is not None:
        logger.info("%s 略過：%s", what, result.skip_reason)
    else:
        logger.info("%s 成功載入 %d 筆", what, result.rows)
```

### 3. `run_daily_price_job`：整個函式換成下面這段

```python
def run_daily_price_job(engine: Engine, market: str) -> None:
    """載入單日日成交；失敗只記 log。

    Args:
        engine: SQLAlchemy Engine
        market: 市場別
    """
    try:
        today = datetime.now(TAIPEI).date()
        _log_job_outcome(
            f"{today} {market} 日成交",
            load_daily_price(engine, market, today),
        )
    except Exception:
        logger.exception("載入 %s 日成交失敗", market)
```

### 4. `run_index_month_job`：整個函式換成下面這段

```python
def run_index_month_job(engine: Engine) -> None:
    """載入當月 TAIEX 指數；失敗只記 log。

    Args:
        engine: SQLAlchemy Engine
    """
    try:
        now = datetime.now(TAIPEI)
        year, month = now.year, now.month
        _log_job_outcome(
            f"{year:04d}-{month:02d} TAIEX 指數",
            load_index_month(engine, year, month, force=True),
        )
    except Exception:
        logger.exception("載入 TAIEX 指數失敗")
```

### 5. `run_adj_factors_job`：整個函式換成下面這段（刪掉函式內的區域 import）

```python
def run_adj_factors_job(engine: Engine) -> None:
    """載入最近 7 天的除權除息；失敗只記 log。

    Args:
        engine: SQLAlchemy Engine
    """
    try:
        today = datetime.now(TAIPEI).date()
        start = today - timedelta(days=7)
        end = today
        _log_job_outcome(
            f"{start} 至 {end} 除權除息",
            load_adj_factors(engine, start, end),
        )
    except Exception:
        logger.exception("載入除權除息失敗")
```

改完後 `scheduler.py` 全檔**不准**再出現函式內的 `from datetime import`。

### 6. 測試（`etl/tests/test_etl_scheduler.py`）

這幾個測試一律用 `monkeypatch` 換掉 `twstock_etl.scheduler` 內被呼叫的 job 函式，
回傳現成的 dataclass，**不需要 DB、不打網路**，斷言也不依賴系統當前日期
（訊息前綴含日期的部分不要放進斷言字串）。

**6.1 改既有 `test_run_index_month_job_success` 的斷言。** 把：

```python
    assert "成功載入 2026-09 TAIEX 指數：3 筆" in caplog.text
```

換成：

```python
    assert "TAIEX 指數 成功載入 3 筆" in caplog.text
```

同時在該測試結尾補一行 `assert "Traceback" not in caplog.text`。

**6.2 改既有 `test_run_adj_factors_job_success` 的斷言。** 把：

```python
    assert "除權除息：2 筆" in caplog.text
```

換成：

```python
    assert "除權除息 成功載入 2 筆" in caplog.text
```

同時在該測試結尾補一行 `assert "Traceback" not in caplog.text`。

**6.3 新增 `test_run_daily_price_job_success`**（放在 `test_run_stock_list_job_error_handling` 之後）：

```python
def test_run_daily_price_job_success(monkeypatch, caplog):
    """測試日成交 wrapper 成功路徑的 log 輸出。"""
    import logging
    from datetime import date

    from twstock_etl.jobs import PriceJobResult
    from twstock_etl.scheduler import run_daily_price_job

    def fake_load(engine, market, trade_date, **kwargs):
        return PriceJobResult(
            market=market,
            trade_date=date(2026, 9, 18),
            rows=4,
            skipped_unknown=1,
            skip_reason=None,
        )

    monkeypatch.setattr("twstock_etl.scheduler.load_daily_price", fake_load)

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    with caplog.at_level(logging.INFO, logger="twstock_etl.scheduler"):
        run_daily_price_job(engine, "TWSE")

    assert "TWSE 日成交 成功載入 4 筆" in caplog.text
    assert "Logging error" not in caplog.text
    assert "TypeError" not in caplog.text
    assert "Traceback" not in caplog.text
```

**6.4 新增 `test_run_daily_price_job_skip`**（第 1 輪 Blocker 1 的回歸測試：略過不可以被記成錯誤，
也不可以印成「成功載入 0 筆」）：

```python
def test_run_daily_price_job_skip(monkeypatch, caplog):
    """被略過時要記「略過」，且不得出現任何 ERROR 紀錄。"""
    import logging
    from datetime import date

    from twstock_etl.jobs import PriceJobResult
    from twstock_etl.scheduler import run_daily_price_job

    def fake_load(engine, market, trade_date, **kwargs):
        return PriceJobResult(
            market=market,
            trade_date=date(2026, 9, 18),
            rows=0,
            skipped_unknown=0,
            skip_reason="已完成，略過",
        )

    monkeypatch.setattr("twstock_etl.scheduler.load_daily_price", fake_load)

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    with caplog.at_level(logging.INFO, logger="twstock_etl.scheduler"):
        run_daily_price_job(engine, "TWSE")

    assert "TWSE 日成交 略過：已完成，略過" in caplog.text
    assert "成功載入" not in caplog.text
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
```

**6.5 新增 `test_run_trading_calendar_job_success`**：

```python
def test_run_trading_calendar_job_success(monkeypatch, caplog):
    """測試交易日曆 wrapper 成功路徑的 log 輸出。"""
    import logging

    from twstock_etl.jobs import CalendarLoadResult
    from twstock_etl.scheduler import run_trading_calendar_job

    def fake_refresh(engine, year, **kwargs):
        return [
            CalendarLoadResult(year=year, days=365, open_days=246, closed_days=119),
            CalendarLoadResult(year=year + 1, days=365, open_days=246, closed_days=119),
        ]

    monkeypatch.setattr(
        "twstock_etl.scheduler.refresh_calendar_with_next_year", fake_refresh
    )

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    with caplog.at_level(logging.INFO, logger="twstock_etl.scheduler"):
        run_trading_calendar_job(engine)

    assert "成功刷新 2 個年份的交易日曆" in caplog.text
    assert "Logging error" not in caplog.text
    assert "TypeError" not in caplog.text
    assert "Traceback" not in caplog.text
```

`test_scheduler_jobs`、`test_scheduler_job_triggers`、`test_run_stock_list_job_error_handling` 不准動。

### 驗收指令

```bash
cd /home/claude/TwStock && .venv/bin/python -m pytest etl/tests/test_etl_scheduler.py -q
# 預期：輸出含 "8 passed"（5 個既有 + 本子任務新增 3 個），0 failed

cd /home/claude/TwStock && grep -n "    from datetime import" etl/twstock_etl/scheduler.py
# 預期：沒有任何輸出（函式內不得有區域 import）

cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) \
  .venv/bin/python -m pytest -rs -q
# 預期：全部 passed、0 failed
```

### 不要做的事

- 不准動 `jobs.py`、`cli.py`。
- 不准改 `build_scheduler` 的 cron 時間、時區或 `next_run_time` 設定。
- 不准把 `run_stock_list_job`／`run_trading_calendar_job` 改成走 `_log_job_outcome`
  （它們回傳的不是這組 dataclass）。

---

## T1-4d　`jobs.py`：`refresh_stock_list`／`refresh_trading_calendar`／`rebuild_calendar_from_index` 補 `etl_job_log`

依賴：T1-4c。這是 T1-4 拆分後的最後一個子任務，也是第 4 輪 Blocker 5。

### 範圍（只准動這兩個檔案）

| 路徑 | 動作 |
| --- | --- |
| `etl/twstock_etl/jobs.py` | 修改：頂層 import 加 `Sequence`、新增 `_write_calendar_year`、改寫 `refresh_stock_list`／`refresh_trading_calendar`／`refresh_calendar_with_next_year`／`rebuild_calendar_from_index` |
| `etl/tests/test_etl_job_records.py` | **新增**（3 個測試） |

`jobs.py` 的 `load_daily_price`／`load_index_month`／`load_adj_factors`／`is_trading_day`
與三個 `*JobResult` dataclass 這個子任務**一律不准動**（T1-4a 已處理）。

### 1. 頂層 import（`etl/twstock_etl/jobs.py`）

在 `import json` 上方（第 3 行之前）加一行：

```python
from collections.abc import Sequence
```

（依 isort 慣例放在標準函式庫區塊；`import json`、`import logging` 之後、`from dataclasses import dataclass` 之前也可以，
只要 `.venv/bin/python -m pytest` 不報錯即可。）

### 2. `refresh_stock_list`：把函式本體包一層 `job_run`

job 名稱 `stock_list_twse` / `stock_list_tpex`（`market.lower()`）、`target_key=market`、`target_date=None`。
**簽名與回傳值不變**，`SourceFormatError` 仍然往外拋（由 `job_run` 記 `failed` 後重拋）。
把 `if html is None:` 到 `return StockLoadResult(...)` 整段換成：

```python
    job_name = f"stock_list_{market.lower()}"
    loaded = 0
    deactivated = 0

    with job_run(engine, job_name, target_key=market) as run:
        if html is None:
            html = fetch_isin_html(market, client)

        records = parse_isin_html(html, market)

        with engine.begin() as conn:
            if deactivate:
                previous = count_active_stocks(conn, market)
                if previous > 0 and len(records) < previous * DEACTIVATE_MIN_RATIO:
                    raise SourceFormatError(
                        f"{market} 本次解析 {len(records)} 筆，低於前次有效筆數 {previous} 的 "
                        f"{DEACTIVATE_MIN_RATIO:.0%}（門檻 {previous * DEACTIVATE_MIN_RATIO:.0f} 筆），拒絕停用缺漏個股"
                    )
                if previous == 0 and len(records) < DEACTIVATE_MIN_ABSOLUTE:
                    raise SourceFormatError(
                        f"{market} 本次解析 {len(records)} 筆，少於初次建庫下限 "
                        f"{DEACTIVATE_MIN_ABSOLUTE} 筆，拒絕停用缺漏個股"
                    )
            loaded = upsert_stocks(conn, records)
            deactivated = deactivate_missing(conn, market, {r.stock_id for r in records}) if deactivate else 0

        run.rows = loaded

    logger.info(
        "刷新 %s 個股清單完成：載入 %d 筆，停用 %d 筆", market, loaded, deactivated
    )
    return StockLoadResult(market=market, records=loaded, deactivated=deactivated)
```

停用保護的兩個錯誤訊息一字不改（既有測試用 `match="初次建庫下限"`、`70%` 斷言）。

### 3. 新增 `_write_calendar_year`

放在 `refresh_trading_calendar` 之前：

```python
def _write_calendar_year(
    engine: Engine, year: int, days: Sequence[CalendarDay]
) -> CalendarLoadResult:
    """把已經 build 好的某年日曆寫入 trading_calendar，並記一列 etl_job_log。

    job_name="trading_calendar"、target_key=f"{year:04d}"、run.rows = len(days)。
    此 job 不會 skip，直接回傳 CalendarLoadResult。

    Args:
        engine: SQLAlchemy Engine
        year: 年份
        days: 該年每一天的 CalendarDay

    Returns:
        CalendarLoadResult
    """
    open_days = sum(1 for d in days if d.is_open)
    closed_days = len(days) - open_days

    with job_run(engine, "trading_calendar", target_key=f"{year:04d}") as run:
        with engine.begin() as conn:
            upsert_calendar(conn, days)
        run.rows = len(days)

    logger.info(
        "刷新 %d 年交易日曆完成：共 %d 天，開市 %d 天，休市 %d 天",
        year,
        len(days),
        open_days,
        closed_days,
    )
    return CalendarLoadResult(
        year=year, days=len(days), open_days=open_days, closed_days=closed_days
    )
```

### 4. `refresh_trading_calendar`：改用 `_write_calendar_year`

把函式本體（`if payload is None:` 到 `return CalendarLoadResult(...)`）換成：

```python
    if payload is None:
        payload = fetch_holiday_schedule(client)

    holidays = parse_holiday_schedule(payload)
    days = build_calendar(year, holidays)

    return _write_calendar_year(engine, year, days)
```

`build_calendar` 的 `SourceFormatError`（年份不符）發生在進 `job_run` 之前，
**不會**留下 `status='failed'` 的列——既有測試 `test_load_calendar_wrong_year` 仍然通過。

### 5. `refresh_calendar_with_next_year`：寫入改走 `_write_calendar_year`

把 `for y in [year, year + 1]:` 這段迴圈換成：

```python
    for y in [year, year + 1]:
        try:
            days = build_calendar(y, holidays)
        except SourceFormatError:
            if y == year + 1:
                logger.info("年份 %d 的交易日曆官方尚未公布，略過", y)
                continue
            raise

        results.append(_write_calendar_year(engine, y, days))
```

重點：`build_calendar` 在 `try` 裡、`_write_calendar_year` 在 `try` 外，
所以「year+1 尚未公布」**不可能**留下 `status='failed'` 的列（D-025）。

### 6. `rebuild_calendar_from_index`：把函式本體包一層 `job_run`

job 名稱 `calendar_from_index`、`target_key=f"{year:04d}"`。把 `with engine.begin() as conn:`
（取 `dates` 那段）到 `return CalendarLoadResult(...)` 整段換成：

```python
    days_total = 0
    open_days = 0
    closed_days = 0

    with job_run(engine, "calendar_from_index", target_key=f"{year:04d}") as run:
        with engine.begin() as conn:
            dates = index_trade_dates(conn, index_id, year)

        if len(dates) < 200:
            raise SourceFormatError(
                f"{year} 年 {index_id} 只有 {len(dates)} 個交易日，"
                f"不足以推算日曆，請先回補指數"
            )

        # 產生該年每一天
        all_days = []
        current_date = date(year, 1, 1)
        end_date = date(year, 12, 31)

        while current_date <= end_date:
            if current_date in dates:
                day = CalendarDay(trade_date=current_date, is_open=True, note=None)
            else:
                day = CalendarDay(
                    trade_date=current_date, is_open=False, note="未開市（由指數回補推得）"
                )
            all_days.append(day)
            current_date = current_date + timedelta(days=1)

        # 寫入
        days_total = len(all_days)
        open_days = sum(1 for d in all_days if d.is_open)
        closed_days = days_total - open_days

        with engine.begin() as conn:
            if overwrite:
                upsert_calendar(conn, all_days)
            else:
                insert_calendar_if_absent(conn, all_days)

        run.rows = days_total

    logger.info(
        "從 %s 指數反推 %d 年日曆完成：共 %d 天，開市 %d 天，休市 %d 天",
        index_id,
        year,
        days_total,
        open_days,
        closed_days,
    )
    return CalendarLoadResult(
        year=year, days=days_total, open_days=open_days, closed_days=closed_days
    )
```

「指數資料不足」是真的失敗，留在 `job_run` 內記 `failed` 後重拋是正確的
（既有測試 `test_rebuild_calendar_from_index` 用 `pytest.raises(SourceFormatError)`，仍然通過）。

### 7. 測試：新增 `etl/tests/test_etl_job_records.py`

```python
"""既有 job 的 etl_job_log 紀錄測試（規格 §3.1、D-025）。"""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from twstock_db.tables import etl_job_log
from twstock_etl.errors import SourceFormatError
from twstock_etl.jobs import refresh_stock_list, refresh_trading_calendar


def _fixture(name: str) -> Path:
    return Path("etl/tests/fixtures") / name


def _job_rows(engine, job_name: str) -> list[tuple[str | None, str]]:
    """回傳該 job_name 的 (target_key, status) 清單。"""
    with engine.begin() as conn:
        return [
            (row.target_key, row.status)
            for row in conn.execute(
                select(etl_job_log.c.target_key, etl_job_log.c.status)
                .where(etl_job_log.c.job_name == job_name)
                .order_by(etl_job_log.c.job_id)
            )
        ]


def test_refresh_stock_list_writes_job_log(clean_db):
    """個股清單成功時要留下一列 stock_list_twse / success。"""
    html = _fixture("isin_twse_strmode2.html").read_text(encoding="utf-8")

    result = refresh_stock_list(clean_db, "TWSE", html=html)

    assert result.market == "TWSE"
    assert _job_rows(clean_db, "stock_list_twse") == [("TWSE", "success")]


def test_refresh_stock_list_guard_writes_failed(clean_db):
    """停用保護觸發時要留下一列 stock_list_twse / failed，且例外仍往外拋。"""
    html = _fixture("isin_twse_strmode2.html").read_text(encoding="utf-8")

    with pytest.raises(SourceFormatError, match="初次建庫下限"):
        refresh_stock_list(clean_db, "TWSE", html=html, deactivate=True)

    assert _job_rows(clean_db, "stock_list_twse") == [("TWSE", "failed")]


def test_refresh_trading_calendar_writes_job_log(clean_db):
    """交易日曆成功時要留下一列 trading_calendar / success。"""
    payload = json.loads(
        _fixture("twse_holiday_schedule_2026.json").read_text(encoding="utf-8")
    )

    result = refresh_trading_calendar(clean_db, 2026, payload=payload)

    assert result.year == 2026
    assert _job_rows(clean_db, "trading_calendar") == [("2026", "success")]
```

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) \
  .venv/bin/python -m pytest etl/tests/test_etl_job_records.py -q
# 預期：輸出含 "3 passed"，0 failed

cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) \
  .venv/bin/python -m pytest -rs -q
# 預期：全部 passed、0 failed；skipped 只有 TimescaleDB 那一筆

# §T1-4 完整 CLI 驗收序列
cd /home/claude/TwStock && export DATABASE_URL=$(scripts/pg_temp.sh reset) && \
  .venv/bin/alembic -c db/alembic.ini upgrade head >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TPEx --file etl/tests/fixtures/isin_tpex_strmode4.html && \
  .venv/bin/python -m twstock_etl.cli load-calendar --year 2026 --file etl/tests/fixtures/twse_holiday_schedule_2026.json && \
  .venv/bin/python -m twstock_etl.cli load-price --market TWSE --date 2026-09-18 --file etl/tests/fixtures/TWSE_price_20260918.json && \
  .venv/bin/python -m twstock_etl.cli load-price --market TPEx --date 2026-09-18 --file etl/tests/fixtures/TPEx_price_20260918.json && \
  .venv/bin/python -m twstock_etl.cli load-index --year 2026 --month 9 --file etl/tests/fixtures/TAIEX_index_202609.json && \
  .venv/bin/python -m twstock_etl.cli load-exright --from 2026-09-01 --to 2026-09-30 --file etl/tests/fixtures/exright_20260901_20260930.json
# 預期（最後四行）：
# loaded market=TWSE date=2026-09-18 rows=4 skipped_unknown=1
# loaded market=TPEx date=2026-09-18 rows=3 skipped_unknown=1
# loaded index=TAIEX month=2026-09 rows=3
# loaded exright from=2026-09-01 to=2026-09-30 rows=2

# 七種 job_name 都要有紀錄，且沒有 failed（第 4 輪 Blocker 5 的驗收查詢）
cd /home/claude/TwStock && /usr/lib/postgresql/16/bin/psql "${DATABASE_URL/postgresql+psycopg/postgresql}" \
  -t -c "SELECT job_name || ' ' || status FROM etl_job_log GROUP BY 1 ORDER BY 1"
# 預期（7 行，順序如下，且不得出現任何 failed）：
#  adj_factor_twse success
#  daily_price_tpex success
#  daily_price_twse success
#  index_daily_taiex success
#  stock_list_tpex success
#  stock_list_twse success
#  trading_calendar success
```

回報時**必須**附上最後那個 SQL 查詢的完整輸出，不可以只貼 `loaded ...` 幾行。

### 不要做的事

- 不准動 `load_daily_price`／`load_index_month`／`load_adj_factors`（T1-4a 已處理）。
- 不准動 `cli.py`、`scheduler.py`、`loaders/job_log.py`、`sources/`、`loaders/price.py`。
- 不准替這三個 job 加 `has_successful_run` 去重或 skip 分支（日曆與個股清單每天都要重刷，
  §3.1 明訂 `run.note` 恆為 `None`）。
- 不准改停用保護的錯誤訊息字串、也不准改既有測試的斷言方向。

---

## T1-5　回補腳本：速率限制、斷點續傳、進度輸出

### 目標

讓使用者能在 Mac 上一次回補 5 年歷史。核心邏輯放在可測試的 `twstock_etl/backfill.py`，`scripts/backfill.py` 只是薄的進入點。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `etl/twstock_etl/backfill.py` | 新增 |
| `scripts/backfill.py` | 新增（`chmod +x`） |
| `etl/tests/test_etl_backfill.py` | 新增 |
| `README.md` | 修改：新增「歷史回補」一節 |

### 1. `twstock_etl/backfill.py`

```python
logger = logging.getLogger(__name__)

DEFAULT_SLEEP_SECONDS = 3.0
DEFAULT_MAX_FAILURES = 10


class RateLimiter:
    """確保兩次請求之間至少間隔 min_interval 秒。"""

    def __init__(self, min_interval: float, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None: ...

    def wait(self) -> None:
        """必要時睡到距離上次 wait() 已滿 min_interval 秒。"""


@dataclass
class BackfillOptions:
    """回補共用選項。"""

    sleep_seconds: float = DEFAULT_SLEEP_SECONDS
    max_failures: int = DEFAULT_MAX_FAILURES
    force: bool = False
    source_dir: Path | None = None   # 離線模式：從目錄讀 JSON，不發 HTTP
    dry_run: bool = False            # 只印要做什麼，不寫 DB、不發 HTTP
    out: TextIO = sys.stdout


@dataclass
class BackfillSummary:
    """回補結果統計。"""

    total: int
    done: int
    skipped: int
    failed: int
    rows: int
    interrupted_at: str | None = None   # 被 Ctrl-C 中斷時，下次該從哪裡續跑


def trading_days(engine: Engine, start: date, end: date) -> list[date]:
    """從 trading_calendar 取出區間內 is_open=true 的日期（升冪）。

    日曆完全沒有涵蓋到這個區間（回傳空 list）時 raise SourceFormatError，
    訊息提示「請先執行 load-calendar 或 backfill calendar」。
    """


def backfill_prices(engine: Engine, market: str, start: date, end: date,
                    options: BackfillOptions) -> BackfillSummary:
    """逐交易日回補 daily_price。"""


def backfill_index(engine: Engine, start_month: str, end_month: str,
                   options: BackfillOptions) -> BackfillSummary:
    """逐月回補 index_daily（start_month / end_month 格式 'YYYY-MM'）。"""


def backfill_exright(engine: Engine, start: date, end: date,
                     options: BackfillOptions) -> BackfillSummary:
    """逐月回補 adj_factor（每次請求一個自然月）。"""


def backfill_calendar(engine: Engine, from_year: int, to_year: int,
                      options: BackfillOptions) -> BackfillSummary:
    """用已回補的 TAIEX 指數反推歷史年度交易日曆（不發 HTTP）。"""
```

共同行為（四個 `backfill_*` 都要照做）：

1. **斷點續傳**：每個工作單位執行前先 `has_successful_run(...)`；已完成且 `force=False` →
   印 `[  12/1250] 2021-01-20 TWSE skip 已完成` 並計入 `skipped`，**不消耗速率限制**。
2. **速率限制**：只有真的要發 HTTP 前才 `limiter.wait()`。`source_dir` 模式下 `min_interval` 一律視為 0。
3. **進度輸出**（每個工作單位一行，寫到 `options.out`，用 `print(..., file=options.out, flush=True)`）：
   ```
   [  12/1250] 2021-01-20 TWSE rows=1024 elapsed=00:00:38 eta=01:02:15
   ```
   - 序號寬度固定 4（`f"[{i:>4d}/{total:>4d}]"`）。
   - `elapsed` / `eta` 格式 `HH:MM:SS`；`eta` 以「已完成單位的平均耗時 × 剩餘單位數」估算，
     還沒有任何完成單位時印 `eta=--:--:--`。
4. **失敗處理**：單一單位拋例外 → 印 `[  13/1250] 2021-01-21 TWSE FAIL <例外訊息第一行>`、
   `failed += 1`；`failed > max_failures` → 印 `失敗次數超過 <n>，中止回補` 並 `raise BackfillAborted`。
   （`class BackfillAborted(Exception)` 定義在本模組。）
5. **中斷**：捕捉 `KeyboardInterrupt`，設定 `summary.interrupted_at = <目前單位的字串>` 後**正常回傳**
   （由 CLI 決定 exit code）。
6. **離線模式 `source_dir`**：不發 HTTP，改讀下列檔名；檔案不存在 → 該單位視為失敗（`FileNotFoundError`）。

   | 回補種類 | 檔名 |
   | --- | --- |
   | price | `<market>_price_<YYYYMMDD>.json`，例 `TWSE_price_20260918.json` |
   | index | `TAIEX_index_<YYYYMM>.json`，例 `TAIEX_index_202609.json` |
   | exright | `exright_<YYYYMMDD>_<YYYYMMDD>.json`（該月第一天與最後一天），例 `exright_20260901_20260930.json` |

7. **`dry_run`**：印 `[  12/1250] 2021-01-20 TWSE dry-run`，不呼叫 job、不寫 DB。
8. 結束時印一行總結：`完成 <done>／跳過 <skipped>／失敗 <failed>，共寫入 <rows> 筆，耗時 HH:MM:SS`。

### 2. `scripts/backfill.py`

```python
#!/usr/bin/env python3
"""TwStock 歷史資料回補工具。用法見 --help。"""
```

`argparse` 子指令（全部共用 `--sleep`、`--force`、`--source-dir`、`--dry-run`、`--max-failures`）：

```
scripts/backfill.py price    --market TWSE --from 2021-01-04 --to 2026-09-18
scripts/backfill.py index    --from 2021-01 --to 2026-09
scripts/backfill.py exright  --from 2021-01-01 --to 2026-09-18
scripts/backfill.py calendar --from-year 2021 --to-year 2025
```

- 讀 `DATABASE_URL` 建 engine（`twstock_db.engine.get_engine()`）。
- `logging.basicConfig(level=logging.WARNING)`——進度訊息走 `print`，不要被 INFO log 洗掉。
- exit code：全部成功 → 0；有失敗但沒超過門檻 → 1；`BackfillAborted` → 2；被 Ctrl-C 中斷 → 130
  （並印 `已中斷，下次執行會從 <interrupted_at> 繼續`）。
- `--help` 裡要寫清楚建議流程：

  ```
  建議順序（第一次回補 5 年）：
    1. python -m twstock_etl.cli load-stocks --market TWSE
    2. python -m twstock_etl.cli load-stocks --market TPEx
    3. python -m twstock_etl.cli load-calendar                      # 今年
    4. scripts/backfill.py index    --from 2021-01 --to 2026-09     # 約 60 次請求
    5. scripts/backfill.py calendar --from-year 2021 --to-year 2025 # 不發請求
    6. scripts/backfill.py price    --market TWSE --from 2021-01-04 --to 2026-09-18
    7. scripts/backfill.py price    --market TPEx --from 2021-01-04 --to 2026-09-18
    8. scripts/backfill.py exright  --from 2021-01-01 --to 2026-09-18
  步驟 6、7 各約 1,200 次請求，--sleep 3 約需 1 小時。可以隨時 Ctrl-C，再執行會從中斷處繼續。
  ```

### 3. 測試 `etl/tests/test_etl_backfill.py`

- `RateLimiter`：注入假的 `clock` 與 `sleep`，驗證第一次 `wait()` 不睡、第二次睡到補滿間隔。
- `backfill_prices`（需要 DB）：`trading_calendar` 只放 2026-09-16～18 開市，
  `options = BackfillOptions(sleep_seconds=0, source_dir=Path("etl/tests/fixtures"), out=io.StringIO())`
  → `summary.total == 3`、`done == 3`、`rows == 12`（TWSE 每天 4 筆）。
- 再跑一次 → `done == 0`、`skipped == 3`，且輸出每行都含 `skip`。
- `source_dir` 少一個檔案 → `failed == 1`，其他兩天仍成功。
- `max_failures=0` 且有失敗 → `pytest.raises(BackfillAborted)`。
- `dry_run=True` → `rows == 0`、DB 內沒有資料、輸出含 `dry-run`。
- `backfill_index` 與 `backfill_exright` 各一個 happy path。
- `backfill_calendar`：先塞 250 筆 2025 年的 `index_daily` 假資料 → `trading_calendar` 出現 365 筆、
  開市 250 天。
- 進度行格式：用 regex `^\[\s*\d+/\s*\d+\] ` 驗證每一行。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed

cd /home/claude/TwStock && export DATABASE_URL=$(scripts/pg_temp.sh reset) && \
  .venv/bin/alembic -c db/alembic.ini upgrade head >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TPEx --file etl/tests/fixtures/isin_tpex_strmode4.html >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-calendar --year 2026 --file etl/tests/fixtures/twse_holiday_schedule_2026.json >/dev/null && \
  .venv/bin/python scripts/backfill.py price --market TWSE --from 2026-09-16 --to 2026-09-18 \
      --source-dir etl/tests/fixtures --sleep 0
# 預期（3 行進度 + 1 行總結）：
# [   1/   3] 2026-09-16 TWSE rows=4 elapsed=... eta=...
# [   2/   3] 2026-09-17 TWSE rows=4 elapsed=... eta=...
# [   3/   3] 2026-09-18 TWSE rows=4 elapsed=... eta=...
# 完成 3／跳過 0／失敗 0，共寫入 12 筆，耗時 00:00:00

cd /home/claude/TwStock && .venv/bin/python scripts/backfill.py price --market TWSE --from 2026-09-16 --to 2026-09-18 \
      --source-dir etl/tests/fixtures --sleep 0
# 預期：三行都是 skip 已完成；總結 完成 0／跳過 3／失敗 0

cd /home/claude/TwStock && .venv/bin/python scripts/backfill.py --help && .venv/bin/python scripts/backfill.py price --help
# 預期：顯示建議順序與全部選項，exit 0
```

### 不要做的事

- 不要用 threading / asyncio 併發抓取——會被來源擋 IP，而且沒必要。
- 不要在腳本裡寫死日期或 token。
- 不要把回補進度存在額外的檔案（`etl_job_log` 就是斷點）。
- 不要改 API 與前端。

---

## T1-6　API：個股明細、日 K（含還原）、指數、ETL 狀態

### 目標

實作 §5 的五個端點，還原價在 API 層即時計算（見 D-018）。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `api/twstock_api/adjust.py` | 新增 |
| `api/twstock_api/price_repository.py` | 新增 |
| `api/twstock_api/etl_repository.py` | 新增 |
| `api/twstock_api/schemas.py` | 修改：追加 schema |
| `api/twstock_api/routers/prices.py`、`indices.py`、`etl.py` | 新增 |
| `api/twstock_api/routers/stocks.py` | 修改：加 `GET /api/stocks/{stock_id}` |
| `api/twstock_api/main.py` | 修改：`include_router` 三個新 router |
| `api/tests/test_api_adjust.py`、`test_api_prices.py`、`test_api_etl.py` | 新增 |

### 1. `adjust.py`（純函式，不碰 DB）

```python
PRICE_FIELDS = ("open", "high", "low", "close", "change")
QUANT = Decimal("0.0001")


def cumulative_factors(
    bars: Sequence[dict[str, Any]], factors: Sequence[tuple[date, Decimal]]
) -> list[Decimal]:
    """對每根 K 棒算出「其後所有除權息係數的乘積」。

    bars 必須依 trade_date 升冪；factors 為 (ex_date, factor) 且依 ex_date 升冪。
    第 i 根 K 棒的係數 = Π{ f | ex_date > bars[i]["trade_date"] }。

    Returns:
        與 bars 等長的 Decimal 清單
    """


def apply_adjustment(
    bars: Sequence[dict[str, Any]], factors: Sequence[tuple[date, Decimal]]
) -> list[dict[str, Any]]:
    """回傳套用還原係數後的新 K 棒清單（不修改輸入）。

    只調整 PRICE_FIELDS，值為 None 就維持 None；
    結果 quantize 到 QUANT（ROUND_HALF_UP）。volume / turnover / transactions 不調整。
    """
```

演算法（O(n+m)，不要寫成雙重迴圈）：

```python
idx = len(factors) - 1
cum = Decimal(1)
out: list[Decimal] = [Decimal(1)] * len(bars)
for i in range(len(bars) - 1, -1, -1):
    while idx >= 0 and factors[idx][0] > bars[i]["trade_date"]:
        cum *= factors[idx][1]
        idx -= 1
    out[i] = cum
```

**除權息當天那根 K 棒不調整**（條件是 `ex_date > trade_date`，不是 `>=`）。

### 2. `price_repository.py`

```python
MAX_LIMIT = 6000
DEFAULT_LIMIT = 2000
DEFAULT_WINDOW_DAYS = 365
INDEX_NAMES = {"TAIEX": "發行量加權股價指數"}


def get_stock(conn: Connection, stock_id: str) -> dict[str, Any] | None:
    """讀 stock 一列（含 is_active）；查無回 None。"""


def latest_price_date(conn: Connection, stock_id: str) -> date | None:
    """該股在 daily_price 的最新 trade_date。"""


def fetch_prices(
    conn: Connection, stock_id: str, start: date, end: date, limit: int
) -> list[dict[str, Any]]:
    """讀日 K，依 trade_date 升冪；超過 limit 時取最新的 limit 筆。

    SQL 用 ORDER BY trade_date DESC LIMIT :limit 取回後在 Python 反轉，
    確保「超過上限時保留最新的資料」。
    """


def fetch_adj_factors(
    conn: Connection, stock_id: str, until: date
) -> list[tuple[date, Decimal]]:
    """讀 ex_date <= until 的除權息係數，依 ex_date 升冪。

    注意上界要用「資料區間的最後一天」，因為只有區間內（含之後）的除權息才會影響區間內的價格；
    實作上直接取該股全部 factor 即可（一檔頂多數十列），但仍要依 ex_date 升冪。
    """


def latest_bar(conn: Connection, stock_id: str) -> dict[str, Any] | None:
    """該股最新一根日 K；沒有回 None。"""


def fetch_index_prices(
    conn: Connection, index_id: str, start: date, end: date, limit: int
) -> list[dict[str, Any]]:
    """讀 index_daily，規則同 fetch_prices。"""
```

全部用 `sqlalchemy.text()` + bind 參數。`NUMERIC` 欄位 psycopg 會回 `Decimal`，保持原樣傳到 router 再轉 `float`。

### 3. `etl_repository.py`

```python
def recent_jobs(conn: Connection, limit: int) -> list[dict[str, Any]]:
    """最近的 etl_job_log，依 started_at 降冪。"""
    # duration_seconds = EXTRACT(EPOCH FROM (finished_at - started_at))，finished_at 為 NULL 時回 None


def job_summary(conn: Connection) -> list[dict[str, Any]]:
    """每個 job_name 的最後一次執行 + 近 7 天失敗次數 + 總執行次數，依 job_name 升冪。"""
```

`job_summary` 的 SQL（參數化，直接照抄）：

```sql
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
```

### 4. `schemas.py` 追加

```python
class PriceBar(BaseModel):
    """一根日 K。"""
    time: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    change: float | None
    volume: int
    turnover: float
    transactions: int


class IndexBar(BaseModel):
    """一根指數日 K。"""
    time: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None


class PriceResponse(BaseModel):
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx", "ESB"]
    adjusted: bool
    from_: date = Field(alias="from")
    to: date
    count: int
    items: list[PriceBar]
    model_config = ConfigDict(populate_by_name=True)


class IndexResponse(BaseModel):
    index_id: str
    name: str
    from_: date = Field(alias="from")
    to: date
    count: int
    items: list[IndexBar]
    model_config = ConfigDict(populate_by_name=True)


class StockDetail(BaseModel):
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx", "ESB"]
    industry: str | None
    listed_date: date | None
    is_etf: bool
    is_active: bool
    latest: PriceBar | None


class EtlJobRun(BaseModel):
    job_id: int
    job_name: str
    target_date: date | None
    target_key: str | None
    status: Literal["running", "success", "failed", "skipped"]
    rows: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None


class EtlJobSummaryItem(BaseModel):
    job_name: str
    last_status: Literal["running", "success", "failed", "skipped"]
    last_target_date: date | None
    last_target_key: str | None
    last_rows: int
    last_started_at: datetime
    last_finished_at: datetime | None
    failed_last_7_days: int
    total_runs: int


class EtlJobListResponse(BaseModel):
    count: int
    items: list[EtlJobRun]


class EtlSummaryResponse(BaseModel):
    count: int
    items: list[EtlJobSummaryItem]
```

`from` 是 Python 保留字，所以用 `from_` + `alias="from"`，並且 router 回傳時用
`response_model_by_alias=True`（FastAPI 預設就是 True），JSON 內的鍵是 `"from"`。
`date` 欄位序列化成 `"YYYY-MM-DD"`，`datetime` 帶時區偏移（psycopg 回來的是 `timestamptz`，已含 tzinfo）。

### 5. Router

`routers/prices.py`：`APIRouter(prefix="/api/stocks", tags=["prices"])`

```python
@router.get("/{stock_id}/prices", response_model=PriceResponse)
def get_prices(
    stock_id: str,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    adj: bool = Query(default=False),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    engine: Engine = Depends(get_db_engine),
) -> PriceResponse: ...
```

流程：
1. `stock = get_stock(conn, stock_id)`；`None` → `HTTPException(404, f"查無此個股：{stock_id}")`。
2. `to` 為 None → `latest_price_date(conn, stock_id)`，再 None → `datetime.now(ZoneInfo("Asia/Taipei")).date()`。
3. `from_` 為 None → `to - timedelta(days=DEFAULT_WINDOW_DAYS)`。
4. `from_ > to` → `HTTPException(422, "from 不可晚於 to")`。
5. `bars = fetch_prices(...)`。
6. `adj` → `factors = fetch_adj_factors(conn, stock_id, to)`；`bars = apply_adjustment(bars, factors)`。
7. 組 `PriceResponse`，`items` 由 `bars` 轉出（`time` 取 `trade_date`，`Decimal` 轉 `float`，`None` 維持 `None`）。

`routers/indices.py`：`APIRouter(prefix="/api/indices", tags=["indices"])`，
`index_id` 先 `.upper()`，不在 `INDEX_NAMES` → `HTTPException(404, f"查無此指數：{index_id}")`。
`to` 預設取該指數最新 `trade_date`，同樣 fallback 到今天。

`routers/etl.py`：`APIRouter(prefix="/api/etl", tags=["etl"])`，
`GET /jobs`（`limit: int = Query(50, ge=1, le=500)`）、`GET /summary`。

`routers/stocks.py` 追加（**放在既有 `search` 之後**，注意 `""` 與 `/{stock_id}` 不會衝突）：

```python
@router.get("/{stock_id}", response_model=StockDetail)
def get_stock_detail(stock_id: str, engine: Engine = Depends(get_db_engine)) -> StockDetail: ...
```

`main.py` 的 `include_router` 順序：`stocks` → `prices` → `indices` → `etl` → `health`。

### 6. 測試

`test_api_adjust.py`（純函式，不需要 DB）：
- 3 根 K 棒 `2026-09-16/17/18`、factor `[(date(2026,9,17), Decimal("0.99"))]`
  → `cumulative_factors` 回 `[Decimal("0.99"), Decimal("1"), Decimal("1")]`。
- `apply_adjustment` 後 09-16 的 `close == Decimal("990.0000")`、`open == Decimal("985.0500")`、
  `high == Decimal("994.9500")`、`low == Decimal("980.1000")`；09-17、09-18 不變。
- `volume` 不變。
- 兩個除權息（`09-17` 0.99 與 `09-18` 0.98）→ 09-16 的係數是 `0.9702`。
- 空 factors → 全部不變。
- `close=None` 的 K 棒 → 仍是 `None`，不拋例外。

`test_api_prices.py`（需要 DB，用 `clean_db` + `TestClient`）：
- 準備資料：`stock` 三筆、`daily_price` 三天 2330、`adj_factor` 一筆（09-17、0.99）。
- `GET /api/stocks/2330/prices?from=2026-09-16&to=2026-09-18` → 200、`count == 3`、
  `items[0]["close"] == 1000.0`、`items[0]["time"] == "2026-09-16"`、`adjusted is False`。
- 加 `&adj=true` → `items[0]["close"] == 990.0`、`items[2]["close"] == 1008.0`、`adjusted is True`。
- `GET /api/stocks/9999/prices` → 404。
- `from > to` → 422。
- 區間內無資料 → 200、`count == 0`。
- `limit=1` → 回最新一天（`2026-09-18`）。
- `GET /api/stocks/2330` → `latest["close"] == 1008.0`。
- `GET /api/indices/taiex/prices` → 200（小寫也行）、`index_id == "TAIEX"`；`GET /api/indices/XXX/prices` → 404。

`test_api_etl.py`：插三筆 `etl_job_log`（success / failed / running）→
`GET /api/etl/jobs?limit=2` 回 2 筆且依 `started_at` 降冪；
`GET /api/etl/summary` 每個 `job_name` 一筆、`failed_last_7_days` 正確、`duration_seconds` 對 `finished_at` 為 NULL 的回 `null`。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed

cd /home/claude/TwStock && export DATABASE_URL=$(scripts/pg_temp.sh reset) && \
  .venv/bin/alembic -c db/alembic.ini upgrade head >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-calendar --year 2026 --file etl/tests/fixtures/twse_holiday_schedule_2026.json >/dev/null && \
  .venv/bin/python scripts/backfill.py price --market TWSE --from 2026-09-16 --to 2026-09-18 --source-dir etl/tests/fixtures --sleep 0 >/dev/null && \
  .venv/bin/python scripts/backfill.py index --from 2026-09 --to 2026-09 --source-dir etl/tests/fixtures --sleep 0 >/dev/null && \
  .venv/bin/python scripts/backfill.py exright --from 2026-09-01 --to 2026-09-30 --source-dir etl/tests/fixtures --sleep 0 >/dev/null && \
  (.venv/bin/uvicorn twstock_api.main:app --host 127.0.0.1 --port 18002 >/tmp/twstock-t16.log 2>&1 & echo $! >/tmp/twstock-t16.pid) && sleep 3 && \
  curl -s 'http://127.0.0.1:18002/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18' | .venv/bin/python -m json.tool && \
  curl -s 'http://127.0.0.1:18002/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18&adj=true' | \
    .venv/bin/python -c 'import json,sys; print([i["close"] for i in json.load(sys.stdin)["items"]])' && \
  curl -s 'http://127.0.0.1:18002/api/indices/TAIEX/prices' | \
    .venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); print(d["count"], d["items"][-1]["close"])' && \
  curl -s 'http://127.0.0.1:18002/api/etl/summary' | \
    .venv/bin/python -c 'import json,sys; print(sorted(i["job_name"] for i in json.load(sys.stdin)["items"]))' ; \
  kill $(cat /tmp/twstock-t16.pid)
# 預期重點：
# adj=false 的三個 close 依序 1000.0 / 995.0 / 1008.0
# adj=true  的三個 close 依序 [990.0, 995.0, 1008.0]
# 指數：3 24780.0
# summary：['adj_factor_twse', 'daily_price_twse', 'index_daily_taiex', 'stock_list_twse', 'trading_calendar']
```

### 不要做的事

- **不要**在 DB 裡新增 `adj_close` 欄位，也不要在 ETL 階段預先算還原價（見 D-018）。
- 不要做週 K／月 K 聚合（`freq` 參數留到 M2）。
- 不要做寫入型端點（手動重跑 ETL 是 M2 以後的事）。
- 不要開 CORS、不要加認證。

---

## T1-7　Web：個股 K 線頁、ETL 狀態頁，與 M1 整合驗收

### 目標

把 `/stock/:id` 占位頁換成真正的 K 線頁，新增 `/admin/etl` 狀態頁，順手修掉 U-6、U-7，並寫出里程碑整合驗收腳本。

### 新增 / 修改檔案

| 路徑 | 動作 |
| --- | --- |
| `web/package.json` | 修改：`dependencies` 加 `"lightweight-charts": "4.2.3"` |
| `web/src/setupTests.ts` | 修改：加 `ResizeObserver` polyfill |
| `web/src/api.ts` | 修改：追加型別與四個 fetch 函式 |
| `web/src/ma.ts` | 新增 |
| `web/src/components/CandleChart.tsx` | 新增 |
| `web/src/pages/StockPage.tsx` | 改寫 |
| `web/src/pages/EtlStatusPage.tsx` | 新增 |
| `web/src/pages/SearchPage.tsx` | 修改：修 U-6、U-7 |
| `web/src/App.tsx` | 修改：加 `/admin/etl` 路由與 header 連結 |
| `web/src/styles.css` | 修改：追加樣式 |
| `web/src/ma.test.ts`、`web/src/pages/StockPage.test.tsx`、`web/src/pages/EtlStatusPage.test.tsx` | 新增 |
| `scripts/verify_prices.py`、`scripts/m1_verify.sh` | 新增（`m1_verify.sh` 要 `chmod +x`） |
| `README.md` | 修改：進度、個股頁、ETL 狀態頁、回補流程 |

### 1. `api.ts` 追加

```ts
export interface PriceBar {
  time: string; open: number | null; high: number | null; low: number | null
  close: number | null; change: number | null
  volume: number; turnover: number; transactions: number
}
export interface PriceResponse {
  stock_id: string; name: string; market: Market; adjusted: boolean
  from: string; to: string; count: number; items: PriceBar[]
}
export interface StockDetail {
  stock_id: string; name: string; market: Market; industry: string | null
  listed_date: string | null; is_etf: boolean; is_active: boolean
  latest: PriceBar | null
}
export interface EtlJobSummaryItem {
  job_name: string; last_status: 'running' | 'success' | 'failed' | 'skipped'
  last_target_date: string | null; last_target_key: string | null; last_rows: number
  last_started_at: string; last_finished_at: string | null
  failed_last_7_days: number; total_runs: number
}
export interface EtlJobRun {
  job_id: number; job_name: string; target_date: string | null; target_key: string | null
  status: 'running' | 'success' | 'failed' | 'skipped'; rows: number; error: string | null
  started_at: string; finished_at: string | null; duration_seconds: number | null
}

export async function fetchStock(stockId: string, signal?: AbortSignal): Promise<StockDetail>
export async function fetchPrices(
  stockId: string,
  params: { from?: string; to?: string; adj?: boolean; limit?: number },
  signal?: AbortSignal,
): Promise<PriceResponse>
export async function fetchEtlSummary(signal?: AbortSignal): Promise<{ count: number; items: EtlJobSummaryItem[] }>
export async function fetchEtlJobs(limit: number, signal?: AbortSignal): Promise<{ count: number; items: EtlJobRun[] }>
```

全部沿用既有 `searchStocks` 的寫法：`fetch(url, { signal })`、非 2xx 丟 `new Error(\`HTTP ${res.status}\`)`。
`fetchStock` 對 404 丟 `new Error('查無此個股')`。

### 2. `ma.ts`

```ts
export interface MaPoint { time: string; value: number }

/** 以收盤價算簡單移動平均；資料不足 period 的位置不輸出點。 */
export function simpleMovingAverage(
  bars: { time: string; close: number | null }[],
  period: number,
): MaPoint[]
```

- `period <= 0` → 丟 `new Error('period 必須大於 0')`。
- `close` 為 `null` 的 K 棒**整段視窗不輸出**（簡單作法：視窗內任一 `close` 為 `null` 就跳過該點）。
- 值四捨五入到小數 4 位：`Math.round(avg * 10000) / 10000`。

### 3. `components/CandleChart.tsx`

```tsx
export interface CandleChartProps {
  bars: PriceBar[]
  maPeriods?: number[]   // 預設 [5, 20, 60]
  height?: number        // 主圖高度，預設 400
  volumeHeight?: number  // 成交量副圖高度，預設 120
}

export default function CandleChart(props: CandleChartProps): JSX.Element
```

實作規則（Lightweight Charts **v4 API**）：

- 兩個 `useRef<HTMLDivElement>`：主圖容器與成交量容器；兩個 `createChart` 實例。
- `useEffect` 依 `[]` 建立圖表、依 `[bars, maPeriods]` 更新資料；`return () => chart.remove()` 清理。
- 主圖：`chart.addCandlestickSeries({ upColor: '#d32f2f', downColor: '#2e7d32', borderUpColor: '#d32f2f', borderDownColor: '#2e7d32', wickUpColor: '#d32f2f', wickDownColor: '#2e7d32' })`
  （**台股習慣紅漲綠跌**）。
- 均線：對每個 `maPeriods` 加一條 `chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false })`，
  顏色依序 `['#f9a825', '#1e88e5', '#8e24aa', '#00897b']`（不足時循環）。
- 成交量：`volumeChart.addHistogramSeries({ priceFormat: { type: 'volume' } })`，
  每根的 `color` 依當日 `close >= open` 取紅／綠。
- 時間軸同步：主圖與量圖各自 `timeScale().subscribeVisibleLogicalRangeChange(...)`，把對方 `setVisibleLogicalRange(range)`；
  用一個 `syncingRef` 布林避免無限迴圈。
- `setData` 時要過濾掉 `open/high/low/close` 任一為 `null` 的 K 棒。
- 用 `ResizeObserver` 監看容器寬度，`chart.applyOptions({ width })`。
- 元件內**不要**自己 fetch 資料。

### 4. `pages/StockPage.tsx`

版面（由上到下）：

1. **標頭**：`{stock_id} {name}`、市場中文（`marketLabel`）、`industry`、ETF 標記；
   右側 `latest` 的收盤價與漲跌（漲紅跌綠，`className="up"` / `"down"`）、成交量（股數除以 1000 顯示為「張」，
   標示單位）。
2. **工具列**：區間按鈕 `3M / 6M / 1Y / 3Y / 5Y`（`aria-pressed` 標示目前選取）、
   還原價 checkbox（`<label>還原價</label>`，預設**開啟**）。
3. **`<CandleChart bars={...} />`**。
4. 載入中 `<p role="status">載入中…</p>`；錯誤 `<p role="alert">載入失敗：{message}</p>`；
   無資料 `<p>這檔目前沒有日 K 資料，請先執行回補。</p>`。

行為：

- `useParams` 取 `stockId`；`useEffect` 依 `[stockId, range, adjusted]` 重新抓
  `fetchStock` 與 `fetchPrices(stockId, { from, adj: adjusted })`（兩支並行 `Promise.all`）。
- `from` 由區間換算：`3M`→90 天、`6M`→180、`1Y`→365、`3Y`→1095、`5Y`→1825，
  以「今天（瀏覽器本地日期）」往前推，格式 `YYYY-MM-DD`；`to` 不傳（讓後端取最新交易日）。
- 每次請求用 `AbortController`，並用**請求序號**（`useRef<number>`）確保只有最後一次請求能寫進 state
  （同時解掉 U-6 的 loading 閃爍）。
- 區間與還原價開關的選擇存進 `localStorage`（鍵 `twstock.stockPage.range`、`twstock.stockPage.adjusted`），
  下次進頁面沿用；讀不到就用預設值。

### 5. `pages/EtlStatusPage.tsx`（路徑 `/admin/etl`）

- 兩個區塊：`<h2>各項工作狀態</h2>`（`fetchEtlSummary`）與 `<h2>最近執行紀錄</h2>`（`fetchEtlJobs(50)`）。
- 摘要表格欄位：工作、最後狀態、目標、筆數、開始時間、耗時、近 7 天失敗次數。
- 紀錄表格欄位：時間、工作、目標、狀態、筆數、耗時、錯誤訊息（超過 80 字截斷並加 `title` 屬性）。
- 狀態用中文顯示：`success`→成功（綠）、`failed`→失敗（紅）、`running`→執行中（藍）、`skipped`→略過（灰）；
  用 `<span className={'status status-' + status}>`。
- 時間顯示成台北時間 `YYYY-MM-DD HH:mm:ss`（用 `new Date(iso).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei', hour12: false })`）。
- 每 30 秒自動重新整理（`setInterval`，`useEffect` 回傳時 `clearInterval`）；另有「立即重新整理」按鈕。
- **唯讀**，沒有「手動重跑」按鈕（M1 範圍外）。

### 6. `App.tsx`、`setupTests.ts`、`SearchPage.tsx` 修改

- `App.tsx`：加 `<Route path="/admin/etl" element={<EtlStatusPage />} />`，header 右側加 `<Link to="/admin/etl">ETL 狀態</Link>`。
- `setupTests.ts` 追加：

  ```ts
  class ResizeObserverMock {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  if (!('ResizeObserver' in globalThis)) {
    ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverMock
  }
  ```

- `SearchPage.tsx`：
  - **U-6**：加 `const reqIdRef = useRef(0)`；每次 `performSearch` 先 `const myId = ++reqIdRef.current`，
    所有 `setResponse` / `setError` / `setLoading(false)` 都包在 `if (myId === reqIdRef.current)` 內。
  - **U-7**：`/` 快捷鍵的判斷改成通用版：

    ```ts
    const el = document.activeElement as HTMLElement | null
    const tag = el?.tagName
    const typing = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el?.isContentEditable === true
    if (e.key === '/' && !typing) { e.preventDefault(); inputRef.current?.focus() }
    ```

### 7. 前端測試

`ma.test.ts`：
- `simpleMovingAverage([...5 根 close 1..5], 5)` → 1 個點、`value === 3`。
- 資料不足 → `[]`；`period = 0` → 丟錯；含 `null` 的視窗不輸出。

`StockPage.test.tsx`：**必須 mock `lightweight-charts`**（jsdom 沒有 canvas 尺寸），檔案最上方放：

```ts
vi.mock('lightweight-charts', () => {
  const series = { setData: vi.fn(), applyOptions: vi.fn(), priceScale: () => ({ applyOptions: vi.fn() }) }
  const timeScale = {
    fitContent: vi.fn(), applyOptions: vi.fn(),
    subscribeVisibleLogicalRangeChange: vi.fn(), unsubscribeVisibleLogicalRangeChange: vi.fn(),
    setVisibleLogicalRange: vi.fn(),
  }
  return {
    createChart: vi.fn(() => ({
      addCandlestickSeries: vi.fn(() => series),
      addLineSeries: vi.fn(() => series),
      addHistogramSeries: vi.fn(() => series),
      timeScale: () => timeScale,
      applyOptions: vi.fn(), resize: vi.fn(), remove: vi.fn(),
    })),
    ColorType: { Solid: 'solid' },
    CrosshairMode: { Normal: 0, Magnet: 1 },
    LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
  }
})
```

測試項目（`global.fetch` 用 `vi.fn()` 依 URL 回不同 payload，並用
`render(<MemoryRouter initialEntries={['/stock/2330']}><Routes>…</Routes></MemoryRouter>)`）：
- 顯示 `2330`、`台積電`、最新收盤 `1008`。
- 點 `5Y` 後，`fetch` 被以含 `from=` 且日期在 5 年前的 URL 呼叫。
- 取消勾選「還原價」後，`fetch` 的 URL 含 `adj=false`。
- API 回 500 → 出現 `role="alert"`。
- `count: 0` → 出現「沒有日 K 資料」字樣。

`EtlStatusPage.test.tsx`：mock fetch 回兩個端點的假資料 → 表格出現 `daily_price_twse`、`成功`、`失敗`；
錯誤訊息被截斷。

### 8. `scripts/verify_prices.py`

```python
def main(argv: list[str] | None = None) -> int:
    """驗證 M1 的 API 回傳值符合 fixture 手算預期。"""
```

參數：`--api-base`（預設 `http://127.0.0.1:18001`）。檢查項（每項印 `OK <名稱>` 或 `FAIL <名稱> <實際值>`）：

| 名稱 | 請求 | 預期 |
| --- | --- | --- |
| `raw-close` | `/api/stocks/2330/prices?from=2026-09-16&to=2026-09-18` | `count == 3`，`[c["close"] for c in items] == [1000.0, 995.0, 1008.0]` |
| `adjusted-close` | 同上 `&adj=true` | `[990.0, 995.0, 1008.0]`，且 `items[0]["open"] == 985.05` |
| `adjusted-flag` | 同上 | `adjusted is True`；不帶 `adj` 時為 `False` |
| `volume-not-adjusted` | 同上 `&adj=true` | `items[0]["volume"] == 25000000` |
| `stock-detail` | `/api/stocks/2330` | `name == "台積電"`、`latest["close"] == 1008.0` |
| `tpex-price` | `/api/stocks/3105/prices?from=2026-09-16&to=2026-09-18` | `count == 3`、最後一筆 `close == 349.0` |
| `index` | `/api/indices/TAIEX/prices?from=2026-09-16&to=2026-09-18` | `count == 3`、最後一筆 `close == 24780.0` |
| `etl-summary` | `/api/etl/summary` | 含 `daily_price_twse`、`daily_price_tpex`、`index_daily_taiex`、`adj_factor_twse` 四個 `job_name`，且它們的 `last_status` 都是 `success` |
| `unknown-stock` | `/api/stocks/9999/prices` | HTTP 404 |

全部通過 → 印 `OK all 9 price checks passed` 回 0；否則印失敗項目與 `FAILED n/9` 回 1。

### 9. `scripts/m1_verify.sh`

`set -euo pipefail`、`ROOT="$(cd "$(dirname "$0")/.." && pwd)"`、獨立叢集
`TWSTOCK_PGDATA=/tmp/twstock-pg-m1`、`TWSTOCK_PGPORT=54331`、API port `18001`、
`trap` 在 EXIT 時 kill uvicorn 並 `pg_temp.sh stop`。步驟：

```
== migrate            alembic upgrade head
== load fixtures      load-stocks TWSE / TPEx、load-calendar 2026
== backfill index     scripts/backfill.py index   --from 2026-09 --to 2026-09 --source-dir <fixtures> --sleep 0
== backfill price     scripts/backfill.py price   --market TWSE --from 2026-09-16 --to 2026-09-18 --source-dir <fixtures> --sleep 0
                      scripts/backfill.py price   --market TPEx --from 2026-09-16 --to 2026-09-18 --source-dir <fixtures> --sleep 0
== backfill exright   scripts/backfill.py exright --from 2026-09-01 --to 2026-09-30 --source-dir <fixtures> --sleep 0
== resume check       再跑一次 price TWSE，輸出必須全部含 skip（用 grep -c skip 確認為 3）
== start api          uvicorn … --port 18001
== verify prices      scripts/verify_prices.py --api-base http://127.0.0.1:18001
M1 VERIFY PASSED
```

`== resume check` 的實作：把第二次回補輸出存到變數，`[ "$(echo "$OUT" | grep -c 'skip')" = "3" ]` 不成立就 `exit 1`。

腳本要能**重複執行**（每次 `pg_temp.sh reset`）。

### 驗收指令

```bash
cd /home/claude/TwStock/web && rm -rf node_modules && npm install && npm test && npm run build
# 預期：測試全部 passed；tsc 零錯誤；vite build 成功

cd /home/claude/TwStock && scripts/m1_verify.sh
# 預期最後幾行：
# OK all 9 price checks passed
# M1 VERIFY PASSED

cd /home/claude/TwStock && scripts/m1_verify.sh >/dev/null && scripts/m1_verify.sh | tail -1
# 預期：可重複執行，仍為 M1 VERIFY PASSED

cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：後端測試全部仍通過（回歸）

cd /home/claude/TwStock && docker compose -f deploy/docker-compose.yml --env-file .env.example config --quiet && echo COMPOSE_OK
# 預期：COMPOSE_OK
```

### 不要做的事

- 不要用 `chart.addSeries(CandlestickSeries, …)`（那是 v5 API，4.2.3 沒有）。
- 不要在 jsdom 測試裡真的建立圖表（一定要 `vi.mock`）。
- 不要做十字線同步顯示數值的浮動面板（M2 副圖一起做）。
- 不要做自選股、排行、選股器、週／月 K 切換。
- 不要 `docker compose up` / `docker build`。
- 不要改 `deploy/docker-compose.yml`（M1 不需要新 service）。

---

## 6. M1 的範圍邊界（全域）

**做**：上市＋上櫃日 K、加權指數（TAIEX）日 K、上市除權息還原係數、5 年回補、個股頁 K 線／均線／成交量、ETL 狀態頁（唯讀）、每日排程。

**不做**（寫在這裡是為了讓 Coder 不要自行發揮）：

| 項目 | 留到 |
| --- | --- |
| 櫃買指數、類股指數 | M2 |
| 上櫃除權息（因此上櫃個股的還原 K 線 M1 等同原始 K 線） | M2 |
| 週 K／月 K（continuous aggregate 或 `freq` 參數） | M2 |
| 三大法人、融資融券、借券、外資持股、集保分散與副圖 | M2 |
| KD／MACD／RSI／布林通道 | M2 |
| 十字線同步數值面板 | M2 |
| ETL 手動重跑（寫入型 API） | M2 |
| 月營收、財報、股利、估值、自選股、排行、選股器 | M3 |
| Redis 快取、Helm chart、備份腳本 | 之後 |

## 7. 留待使用者本機驗證（本環境做不到）

| # | 項目 | 指令 / 方式 | 通過標準 |
| --- | --- | --- | --- |
| V-1 | TimescaleDB hypertable 真的建起來（解 U-2 的另一半） | `docker compose -f deploy/docker-compose.yml --env-file .env up -d --build` 後 `docker compose … exec db psql -U twstock -d twstock -c "SELECT hypertable_name FROM timescaledb_information.hypertables"` | 看得到 `daily_price`、`index_daily`。若 migration 報錯，看 log 裡是走 `by_range` 還是舊簽名 |
| V-2 | 上市日成交真實格式 | `python -m twstock_etl.cli load-price --market TWSE --date <最近交易日>` | `rows` 約 1,000–1,100；無 `SourceFormatError` |
| V-3 | **上櫃日成交真實格式（風險最高）** | `python -m twstock_etl.cli load-price --market TPEx --date <最近交易日>` | `rows` 約 800+。若新版端點失敗會自動退回舊版，log 會有 warning；兩者都失敗就把真實回應存成 fixture 回報 Architect |
| V-4 | 加權指數 | `python -m twstock_etl.cli load-index` | 當月交易日數（約 20） |
| V-5 | 除權息 | `python -m twstock_etl.cli load-exright --from <上月1日> --to <上月底>` | 7–8 月（除權息旺季）應有數百筆 |
| V-6 | 5 年回補實跑 | 照 `scripts/backfill.py --help` 的建議順序 | 每個步驟可 Ctrl-C 後續跑；`daily_price` 總筆數約 2,000 檔 × 1,220 交易日 ≈ 240 萬列 |
| V-7 | 還原價正確性抽樣 | 開 `http://localhost:8080/stock/2330`，勾「還原價」，與券商軟體或 FinMind 的還原價比對最近一次除權息前後 | 誤差在小數點後幾位內（四捨五入差） |
| V-8 | 排程每天自動更新 | 隔天 09:00 開 `http://localhost:8080/admin/etl` | `daily_price_twse` / `daily_price_tpex` 的 `last_status` 是 `success`、`last_target_date` 是前一個交易日 |

若真實格式與 fixture 不符：以真實回應更新 `etl/tests/fixtures/`、調整 parser，並在 `docs/decisions.md` 補記。

## 8. M0 未解問題在 M1 的處理

| # | M0 問題 | M1 處理 |
| --- | --- | --- |
| U-1 | 真實來源格式未驗證 | 仍無法在本環境解決。M1 把風險收斂成 §7 的 V-2～V-5 逐項檢查，並讓上櫃端點有備援路徑（D-016） |
| U-2 | TimescaleDB 路徑未實跑 | T1-1 加 mock 測試與條件跳過測試，並把 `create_hypertable_if_available` 改成新舊簽名雙保險（D-019）。**實跑仍留 V-1**，文件已寫明 |
| U-3 | 停用保護是絕對門檻 500 筆 | T1-4 改成相對比例 70%（D-020） |
| U-4 | `docker build` 從未執行 | 仍留給使用者（V-1）。M1 沒有改 Dockerfile，風險不變 |
| U-5 | 交易日曆跨年空窗、無歷史年度 | T1-4 的 `refresh_calendar_with_next_year`（每天刷新今年＋明年）與 `rebuild_calendar_from_index`（歷史年度由指數反推），T1-5 提供 `backfill.py calendar`（D-021） |
| U-6 | 搜尋頁 loading 閃爍 | T1-7 用請求序號修掉 |
| U-7 | `/` 快捷鍵判斷不通用 | T1-7 改成通用判斷（個股頁有第二個輸入元件了） |
| U-8 | 搜尋沒有模糊比對與索引 | 不處理，維持 M2 再評估 |

## 任務狀態

| 任務 | 標題 | 相依 | 狀態 | 審查報告 |
| --- | --- | --- | --- | --- |
| T1-1 | Migration 0002：價格三表 + etl_job_log，與 hypertable 雙簽名 | — | DONE | `docs/reviews/T1-1.md` |
| T1-2 | 來源 parser：日成交（上市／上櫃）、加權指數、除權除息 | T1-1（models 共用，可平行但順序照排） | DONE | `docs/reviews/T1-2.md` |
| T1-3 | Loader：價格三表寫入、未知代號過濾、etl_job_log 紀錄 | T1-1、T1-2 | DONE | `docs/reviews/T1-3.md` |
| T1-4 | Job、CLI、排程：每日盤後自動更新，並修掉 U-3 與 U-5 | T1-3 | SPLIT（拆成 T1-4a～T1-4d） | `docs/reviews/T1-4.md` |
| T1-4a | `jobs.py`：三個價格 job 改單一 `return`，`load_index_month` 加 `now` 注入 | T1-4 | DONE | `docs/reviews/T1-4a.md` |
| T1-4b | `cli.py`：`load-index`／`load-exright` 的 skip 輸出對齊 §4 表格 | T1-4a | DONE | `docs/reviews/T1-4b.md` |
| T1-4c | `scheduler.py`：`_log_job_outcome` helper 與四個 wrapper 的 log 測試 | T1-4a | DONE | `docs/reviews/T1-4c.md` |
| T1-4d | `jobs.py`：個股清單／交易日曆／指數反推日曆補 `etl_job_log` | T1-4c | DONE | `docs/reviews/T1-4d.md` |
| T1-5 | 回補腳本：速率限制、斷點續傳、進度輸出 | T1-4a～T1-4d 全數 DONE | DONE | 審查報告 `docs/reviews/T1-5.md`（第 3 輪 APPROVE）；Coder 自述見 `docs/reviews/T1-5-coder-notes.md` |
| T1-6 | API：個股明細、日 K（含還原）、指數、ETL 狀態 | T1-5（驗收要用回補後的資料） | TODO（尚未實作，`api/twstock_api/` 只有 M0 的 health／stocks） | — |
| T1-7 | Web：個股 K 線頁、ETL 狀態頁，與 M1 整合驗收 | T1-6 | TODO | — |

> **狀態表修正紀錄（2026-09-19，Architect）**：上一輪流程中 Reviewer 誤把主對話裡使用者詢問進度的訊息當成中止指令，
> T1-4c、T1-4d、T1-5、T1-6 都沒有真的審查，狀態表卻被標成 BLOCKED。
> 本表已依 git 與實際檔案內容重建為真實狀態：`IN_REVIEW` 表示程式已進 main 但尚未審查，`TODO` 表示完全沒做。
> `0fe1ca4`、`21bc9c9` 兩個 commit 的 BLOCKED 標記是誤標，已由本次修正取代。緣由與防範見 `docs/decisions.md` D-027。
