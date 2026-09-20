# M2 籌碼 規格

- 里程碑：M2 籌碼（見 `docs/plan.md`「開發里程碑」）
- 作者：Architect（claude-opus-5）｜ 日期：2026-09-21
- 前一里程碑：`docs/specs/M1-price.md`、驗收報告 `docs/reports/M1.md`
- 相關決策：`docs/decisions.md`（沿用 D-001 ～ D-028，本里程碑新增 **D-029 ～ D-039**）

## 0. 目標與完成標準

M2 交付「個股頁的副圖跟主圖同一條十字線，滑到哪天所有副圖與讀數面板都顯示那天的籌碼數字」：

1. 四張籌碼資料表：`institutional_daily`（三大法人）、`margin_daily`（融資融券＋借券）、`foreign_holding`（外資持股）、`shareholding_dist`（集保股權分散，週頻）。
2. ETL：三大法人（上市／上櫃）、融資融券（上市／上櫃）、借券賣出（上市）、外資持股（上市）、集保股權分散（全市場）的 parser、loader、job、CLI、排程、回補。
3. **集保股權分散的每週排程在 T2-3 完成時就要能動**——官方只留最新一週，漏抓補不回來（見 §0.1）。
4. API：`GET /api/stocks/{id}/institutional`、`/margin`、`/foreign-holding`、`/shareholding`。
5. Web：個股頁多 pane 副圖（成交量、三大法人買賣超、融資融券餘額）與主圖**十字線同步**＋讀數面板；「籌碼」分頁（集保大戶比例趨勢、外資持股趨勢、法人連續買賣天數）。
6. 順手清掉 M1 的技術債 U-9（`scripts/` 不在映像裡）、U-12（沒有備份腳本）、U-14（`daily_price` 缺 `(stock_id, trade_date DESC)` 索引）。

**里程碑完成標準（本環境版本）**，兩條都要成立：

- `scripts/m2_verify.sh` 最後一行輸出 `M2 VERIFY PASSED`（後端端到端：臨時 PostgreSQL → migration → fixture 離線載入五類籌碼 → 啟動 API → 籌碼數值核對 → 再跑一次回補全部 skip）。
- `cd web && npm test` 內 `src/chartSync.test.ts` 與 `src/components/ChartStack.test.tsx` 全數通過——**這兩支測試就是「副圖與主圖十字線同步」這條完成標準的可執行版本**（十字線事件進來時，其他 pane 收到 `setCrosshairPosition`，讀數面板切到該日數字）。

真實來源連線、`docker compose up`、TimescaleDB hypertable、瀏覽器目視仍留使用者本機（見 §7 的 V-9 ～ V-18）。

### 0.1 為什麼集保排在第 3 個任務

`docs/plan.md`：集保開放資料「只有最新一週，**漏抓就補不回來**」。所以 M2 的排序不是照資料重要性，而是照「錯過的成本」：

- T2-1（技術債）與 T2-2（migration）是 T2-3 的硬相依：沒有 `shareholding_dist` 表就寫不進去。
- **T2-3 一通過審查，使用者就應該在 Mac 上啟動 `etl` 排程**（或每週六手動跑一次 `load-shareholding`），不必等整個 M2 做完。這件事寫進 T2-3 的驗收回報。
- 其餘籌碼（法人／融資券／借券／外資持股）官方都能帶日期查歷史，晚做只是回補時間長一點，不會永久缺資料。

---

## 1. 共用規則（每個任務都適用）

### 1.1 環境事實（與 M1 相同，再確認一次）

| 項目 | 值 |
| --- | --- |
| Repo 根目錄 | `/home/claude/TwStock`（以下簡稱「根目錄」） |
| Python | 本機 `python3` = 3.11（`.venv`）；Docker 映像用 3.12。**程式必須相容 3.11** |
| Node | 22（npm 10） |
| PostgreSQL | 16，執行檔在 `/usr/lib/postgresql/16/bin`，**沒有 TimescaleDB**；臨時叢集用 `scripts/pg_temp.sh` |
| 網路 | pypi / npm 可用；TWSE、TPEx、**TDCC**、MOPS、FinMind **連不到**（一律用 `etl/tests/fixtures/` 測） |
| Docker | 可用但無法 pull / build 映像；只能 `docker compose -f deploy/docker-compose.yml --env-file .env.example config --quiet` |
| git | branch `main`，**只 commit，不要 push**；**Coder 不得 commit**（D-027） |

### 1.2 慣例（沿用 M1 §1.2，重點重貼）

- Bash 每次呼叫 cwd 會重置：**所有指令都用 `cd /home/claude/TwStock && ...` 開頭**。
- 一律用 `.venv/bin/python -m pytest`、`.venv/bin/alembic`，不要用系統 pip。
- 文件、註解、log 訊息、錯誤訊息用繁體中文；識別字用英文。
- 每個 Python 函式都要有型別註記；公開函式要有一行繁中 docstring。
- `logging.getLogger(__name__)`；函式庫程式不要 `print`（只有 `cli.py`、`twstock_etl/backfill.py` 的進度輸出函式與 `scripts/` 可以 print）。
- SQL 一律參數化，**禁止** f-string／`%` 拼接使用者輸入。
- 版本一律精確鎖定（`==`），照 §1.3，不要自行升級。
- 測試檔名在整個 repo 內唯一；測試目錄不要放 `__init__.py`。
- **股數一律 `int`（單位「股」）、比率一律 `decimal.Decimal`**，不要用 `float` 做任何數值運算（只有輸出 JSON 時才轉 `float`）。
- **ETL job 函式一律回傳 frozen dataclass，欄位含 `rows: int` 與 `skip_reason: str | None`；全專案禁止 `except JobSkipped`；函式只能有一個 `return`，回傳值用到的區域變數在進 `with job_run(...)` 之前先給預設值**（D-028，M1 因為這條沒寫清楚被退回三輪）。
- **時間相依的分支一律用可注入的 `now` 參數**，不在分支裡直接呼叫 `datetime.now()`（D-026）。
- **不要動 M1 已通過審查的程式邏輯**，本規格明確列出的修改點除外。
- 完成後依 `.claude/agents/coder.md` 格式回報，並把本文件底部狀態表中該任務改為 `IN_REVIEW`（這是 Coder 唯一可以改本文件的地方）。**Coder 不得執行 `git add` / `git commit`**。

### 1.3 版本

**Python 依賴不新增任何套件**（`csv`、`decimal`、`json` 都是標準庫）。**前端依賴也不新增、不升級**（`lightweight-charts@4.2.3` 已在 `web/package.json`，M1 的 U-13 npm audit 升級延到 M3，見 §8）。

前端只准用 **Lightweight Charts v4 API**：`chart.addCandlestickSeries()` / `addLineSeries()` / `addHistogramSeries()` / `chart.setCrosshairPosition(price, time, series)` / `chart.clearCrosshairPosition()` / `chart.subscribeCrosshairMove(handler)`。**不要**用 v5 的 `chart.addSeries(CandlestickSeries, …)`。Architect 已在本機 `web/node_modules/lightweight-charts/dist/typings.d.ts` 確認 `setCrosshairPosition`、`clearCrosshairPosition`、`subscribeCrosshairMove`、`PriceScaleOptions.minimumWidth` 四者都存在。

### 1.4 M2 結束時新增／修改的檔案

```
TwStock/
├── db/
│   ├── twstock_db/tables.py                          # T2-2 改：加 4 張表
│   ├── migrations/versions/0003_daily_price_index.py # T2-1 新增
│   └── migrations/versions/0004_chip_tables.py       # T2-2 新增
├── etl/
│   ├── Dockerfile                                    # T2-1 改：COPY scripts
│   ├── twstock_etl/models.py                         # T2-2 改：加 5 個 dataclass
│   ├── twstock_etl/cli.py                            # T2-1 改（backfill 子指令）、T2-3 改（load-shareholding）、T2-6 改（load-chip）
│   ├── twstock_etl/loaders/job_log.py                # T2-3 改：加 JobRun.set_target
│   ├── twstock_etl/sources/tdcc.py                   # T2-3 新增（集保 CSV）
│   ├── twstock_etl/loaders/shareholding.py           # T2-3 新增
│   ├── twstock_etl/sources/report.py                 # T2-4 改：加 find_field_all
│   ├── twstock_etl/sources/institutional.py          # T2-4 新增（上市 + 上櫃三大法人）
│   ├── twstock_etl/sources/margin.py                 # T2-5 新增（上市 + 上櫃融資融券）
│   ├── twstock_etl/sources/twse_sbl.py               # T2-5 新增（借券賣出）
│   ├── twstock_etl/sources/twse_foreign.py           # T2-5 新增（外資持股）
│   ├── twstock_etl/loaders/chip.py                   # T2-6 新增（三表 upsert）
│   ├── twstock_etl/chip_sources.py                   # T2-6 新增（來源登錄表）
│   ├── twstock_etl/jobs.py                           # T2-3 改（load_shareholding）、T2-6 改（load_chip_daily）
│   ├── twstock_etl/scheduler.py                      # T2-3 改（週末集保）、T2-6 改（籌碼 6 個 job）
│   ├── twstock_etl/backfill.py                       # T2-6 改：加 backfill_chip
│   └── tests/fixtures/…                              # T2-3 新增 1 個 CSV、T2-4 新增 5 個 JSON、T2-5 新增 7 個 JSON
├── api/
│   ├── twstock_api/chip_repository.py                # T2-7 新增
│   ├── twstock_api/routers/chips.py                  # T2-7 新增
│   ├── twstock_api/schemas.py                        # T2-7 改：加 schema
│   └── twstock_api/main.py                           # T2-7 改：掛 chips router
├── web/
│   ├── src/api.ts                                    # T2-8 改：加型別與 fetch 函式
│   ├── src/chartSync.ts                              # T2-8 新增（十字線同步純函式）
│   ├── src/chipMath.ts                               # T2-8 新增（連續買賣天數等純計算）
│   ├── src/components/ChartStack.tsx                 # T2-8 新增（取代 CandleChart.tsx）
│   ├── src/components/CandleChart.tsx                # T2-8 刪除
│   ├── src/components/ChipTab.tsx                    # T2-8 新增（含自寫的 Sparkline）
│   ├── src/pages/StockPage.tsx                       # T2-8 改：分頁 + 副圖開關
│   ├── src/styles.css                                # T2-8 改
│   └── src/*.test.ts(x)                              # T2-8 新增 4 支、改寫 1 支
└── scripts/
    ├── backfill.py                                   # T2-1 改：薄包裝呼叫 cli
    ├── backup.sh                                     # T2-1 新增
    ├── verify_chips.py                               # T2-7 新增
    └── m2_verify.sh                                  # T2-7 新增
```

### 1.5 任務順序

```
T2-1 技術債 ─► T2-2 migration ─► T2-3 集保端到端（排程可動）─► T2-4 法人 parser
     ─► T2-5 融資券/借券/外資持股 parser ─► T2-6 loader+job+CLI+排程+回補
     ─► T2-7 API + 後端整合驗收 ─► T2-8 前端副圖與籌碼分頁
```

一次只做一個任務；前一個任務 Reviewer `APPROVE` 後才開始下一個。

> **給 Architect 的備註**：T2-8 是本里程碑最大的一個任務。若第 1 輪審查出現 Blocker，直接照 M1 的 T1-4 前例拆成 **T2-8a（`chartSync.ts` + `ChartStack.tsx` 副圖與十字線同步）** 與 **T2-8b（`ChipTab.tsx` 籌碼分頁 + `StockPage` 分頁化）**，不要在同一個任務上來回第三輪。

---

## 2. 資料來源與端點（本里程碑唯一認可的來源）

| # | 用途 | 端點 | 參數 | 回應形狀 | 備註 |
| --- | --- | --- | --- | --- | --- |
| S1 | 三大法人（上市） | `https://www.twse.com.tw/rwd/zh/fund/T86` | `date=YYYYMMDD`、`selectType=ALL`、`response=json` | 頂層單表 `{"stat","fields","data"}` | 一次拿全市場 |
| S2 | 三大法人（上櫃，新版） | `https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade` | `type=Daily`、`sect=EW`、`date=YYYY/MM/DD`、`response=json` | `tables` 信封 | **風險最高**；失敗自動退回 S3 |
| S3 | 三大法人（上櫃，舊版備援） | `https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php` | `l=zh-tw`、`se=EW`、`t=D`、`d=RRR/MM/DD`（民國）、`o=json` | `{"aaData":[[…]]}` | 欄位靠固定順序 |
| S4 | 融資融券（上市） | `https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN` | `date=YYYYMMDD`、`selectType=ALL`、`response=json` | `tables` 信封（多張表，取含「股票代號」那張） | 數量單位是**張**，見 D-036 |
| S5 | 融資融券（上櫃，新版） | `https://www.tpex.org.tw/www/zh-tw/margin/balance` | `date=YYYY/MM/DD`、`response=json` | `tables` 信封 | 失敗自動退回 S6 |
| S6 | 融資融券（上櫃，舊版備援） | `https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php` | `l=zh-tw`、`d=RRR/MM/DD`、`o=json` | `{"aaData":[[…]]}` | 欄位靠固定順序 |
| S7 | 借券賣出餘額（上市） | `https://www.twse.com.tw/rwd/zh/SBL/TWT93U` | `date=YYYYMMDD`、`response=json` | 單表或 `tables` 信封 | 單位是**股**，不轉換 |
| S8 | 外資持股（上市） | `https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS` | `date=YYYYMMDD`、`selectType=ALLBUT0999`、`response=json` | 單表或 `tables` 信封 | 單位是**股** |
| S9 | 集保股權分散（全市場） | `https://opendata.tdcc.com.tw/getOD.ashx` | `id=1-5` | **CSV**（UTF-8，第一列表頭），不是 JSON | 官方只留最新一週 |

- 上櫃借券與上櫃外資持股**不在 M2 範圍**（D-029），因此 `margin_daily.sbl_*` 與 `foreign_holding` 在 M2 只有上市資料。
- S1 ～ S8 全部沿用 M1 的 `sources/report.py`（`extract_table` / `find_field` / `is_no_trade`）與 `numbers.py`（`clean_cell` / `parse_decimal` / `parse_int`）。**不要另外寫一套信封解析。**
- 欄位一律用 `find_field(fields, "候選名A", "候選名B")` 依名稱找，**不要寫死索引**（S3、S6 兩個舊版備援端點沒有 `fields`，才用固定順序，且要在註解寫明順序來源）。

## 3. M2 資料表 DDL（T2-1 建索引、T2-2 建表；其他任務查閱用）

```sql
-- T2-1（migration 0003）：U-14。個股區間查詢與 ORDER BY trade_date DESC LIMIT 1 專用。
CREATE INDEX ix_daily_price_stock_date_desc ON daily_price (stock_id, trade_date DESC);

-- T2-2（migration 0004）------------------------------------------------------

-- 三大法人買賣超（股）。hypertable，按月分區。
CREATE TABLE institutional_daily (
    stock_id     VARCHAR(10) NOT NULL,
    trade_date   DATE        NOT NULL,
    foreign_buy  BIGINT      NOT NULL DEFAULT 0,   -- 外資＝外陸資＋外資自營商（D-035）
    foreign_sell BIGINT      NOT NULL DEFAULT 0,
    foreign_net  BIGINT      NOT NULL DEFAULT 0,
    trust_buy    BIGINT      NOT NULL DEFAULT 0,   -- 投信
    trust_sell   BIGINT      NOT NULL DEFAULT 0,
    trust_net    BIGINT      NOT NULL DEFAULT 0,
    dealer_buy   BIGINT      NOT NULL DEFAULT 0,   -- 自營商＝自行買賣＋避險（D-035）
    dealer_sell  BIGINT      NOT NULL DEFAULT 0,
    dealer_net   BIGINT      NOT NULL DEFAULT 0,
    total_net    BIGINT      NOT NULL DEFAULT 0,   -- 官方「三大法人買賣超股數」原值，供核對
    source       VARCHAR(8)  NOT NULL,             -- TWSE / TPEx
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_id, trade_date),
    CONSTRAINT ck_institutional_daily_source CHECK (source IN ('TWSE', 'TPEx'))
);
CREATE INDEX ix_institutional_daily_trade_date ON institutional_daily (trade_date);
-- create_hypertable_if_available(conn, "institutional_daily", "trade_date", "1 month")

-- 融資融券 + 借券（股）。hypertable，按月分區。
CREATE TABLE margin_daily (
    stock_id            VARCHAR(10) NOT NULL,
    trade_date          DATE        NOT NULL,
    margin_buy          BIGINT      NOT NULL DEFAULT 0,   -- 融資買進
    margin_sell         BIGINT      NOT NULL DEFAULT 0,   -- 融資賣出
    margin_redeem       BIGINT      NOT NULL DEFAULT 0,   -- 現金償還
    margin_prev_balance BIGINT      NOT NULL DEFAULT 0,   -- 融資前日餘額
    margin_balance      BIGINT      NOT NULL DEFAULT 0,   -- 融資今日餘額
    margin_limit        BIGINT,                           -- 融資限額；無資料為 NULL
    short_buy           BIGINT      NOT NULL DEFAULT 0,   -- 融券買進（回補）
    short_sell          BIGINT      NOT NULL DEFAULT 0,   -- 融券賣出
    short_redeem        BIGINT      NOT NULL DEFAULT 0,   -- 現券償還
    short_prev_balance  BIGINT      NOT NULL DEFAULT 0,
    short_balance       BIGINT      NOT NULL DEFAULT 0,
    short_limit         BIGINT,
    offset_amount       BIGINT      NOT NULL DEFAULT 0,   -- 資券互抵
    sbl_sell            BIGINT,                           -- 借券賣出當日（S7，只有上市）
    sbl_balance         BIGINT,                           -- 借券賣出餘額（S7，只有上市）
    source              VARCHAR(8)  NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_id, trade_date),
    CONSTRAINT ck_margin_daily_source CHECK (source IN ('TWSE', 'TPEx'))
);
CREATE INDEX ix_margin_daily_trade_date ON margin_daily (trade_date);
-- create_hypertable_if_available(conn, "margin_daily", "trade_date", "1 month")

-- 外資持股（只有上市）。hypertable，按月分區。
CREATE TABLE foreign_holding (
    stock_id         VARCHAR(10) NOT NULL,
    trade_date       DATE        NOT NULL,
    issued_shares    BIGINT,                              -- 發行股數
    holding_shares   BIGINT      NOT NULL DEFAULT 0,      -- 全體外資及陸資持股股數
    available_shares BIGINT,                              -- 尚可投資股數
    holding_ratio    NUMERIC(8,4),                        -- 持股比率（%）
    available_ratio  NUMERIC(8,4),                        -- 尚可投資比率（%）
    limit_ratio      NUMERIC(8,4),                        -- 法令投資上限比率（%）
    source           VARCHAR(8)  NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_id, trade_date),
    CONSTRAINT ck_foreign_holding_source CHECK (source IN ('TWSE', 'TPEx'))
);
CREATE INDEX ix_foreign_holding_trade_date ON foreign_holding (trade_date);
-- create_hypertable_if_available(conn, "foreign_holding", "trade_date", "1 month")

-- 集保股權分散（週頻）。hypertable，按年分區。
CREATE TABLE shareholding_dist (
    stock_id   VARCHAR(10)  NOT NULL,
    week_date  DATE         NOT NULL,                     -- 資料日期（通常是週五）
    level      SMALLINT     NOT NULL,                     -- 1–15 級距、16 合計、17 差異數調整
    holders    INTEGER      NOT NULL DEFAULT 0,           -- 人數
    shares     BIGINT       NOT NULL DEFAULT 0,           -- 股數
    ratio      NUMERIC(8,4) NOT NULL DEFAULT 0,           -- 占集保庫存數比例（%）
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_id, week_date, level),
    CONSTRAINT ck_shareholding_dist_level CHECK (level BETWEEN 1 AND 17)
);
CREATE INDEX ix_shareholding_dist_week ON shareholding_dist (week_date);
-- create_hypertable_if_available(conn, "shareholding_dist", "week_date", "1 year")
```

集保持股分級對照（`level` 的語意，前端與 API 都照這張表）：

| level | 級距（股） | level | 級距（股） |
| --- | --- | --- | --- |
| 1 | 1–999 | 9 | 50,001–100,000 |
| 2 | 1,000–5,000 | 10 | 100,001–200,000 |
| 3 | 5,001–10,000 | 11 | 200,001–400,000 |
| 4 | 10,001–15,000 | 12 | 400,001–600,000 |
| 5 | 15,001–20,000 | 13 | 600,001–800,000 |
| 6 | 20,001–30,000 | 14 | 800,001–1,000,000 |
| 7 | 30,001–40,000 | 15 | 1,000,001 以上 |
| 8 | 40,001–50,000 | 16 | 合計 ／ 17 差異數調整 |

**大戶＝level 12–15（400 張以上）、散戶＝level 1–4（15 張以下）**（D-038）。

## 4. job 名稱（全專案唯一，T2-3 之後都用這組字串）

沿用 M1 §4 的七個名稱，M2 新增七個：

| `job_name` | 由誰寫入 | `target_date` | `target_key` | 說明 |
| --- | --- | --- | --- | --- |
| `institutional_twse` / `institutional_tpex` | 排程、CLI、回補 | 交易日 | NULL | 三大法人 |
| `margin_twse` / `margin_tpex` | 排程、CLI、回補 | 交易日 | NULL | 融資融券 |
| `sbl_twse` | 排程、CLI、回補 | 交易日 | NULL | 借券賣出（只有上市） |
| `foreign_holding_twse` | 排程、CLI、回補 | 交易日 | NULL | 外資持股（只有上市） |
| `shareholding_tdcc` | 排程、CLI | **資料週五日期**（解析後才知道，用 `JobRun.set_target`，D-033） | NULL | 集保股權分散 |

`job_name` 的組成規則固定為 `{kind}_{market.lower()}`，`kind ∈ {institutional, margin, sbl, foreign_holding}`；集保是唯一的例外（`shareholding_tdcc`）。

## 5. API 契約（T2-7 實作，T2-8 查閱用）

所有端點都在 `/api` 底下、同源、不開 CORS。日期一律 `YYYY-MM-DD` 字串；股數一律 JSON 整數；比率一律 JSON 數字（後端由 `Decimal` 轉 `float`，四捨五入到小數第 4 位）。
`from` / `to` / `limit` 的預設值與錯誤處理**完全比照 M1 §5.2**：`to` 預設為該股在該表的最新日期（完全沒資料時為台北時間今天），`from` 預設為 `to` 往前 365 天，`from > to` → `422`，個股不存在 → `404 {"detail":"查無此個股：9999"}`，個股存在但區間內無資料 → `200` 且 `count: 0`、`items: []`。`items` 一律依時間**升冪**。

### 5.1 `GET /api/stocks/{stock_id}/institutional`

參數：`from`、`to`、`limit`（1–6000，預設 2000）。

```json
{
  "stock_id": "2330", "name": "台積電", "market": "TWSE",
  "from": "2026-09-16", "to": "2026-09-18", "count": 1,
  "items": [
    {"time": "2026-09-18",
     "foreign_buy": 30000000, "foreign_sell": 18000000, "foreign_net": 12000000,
     "trust_buy": 3000000, "trust_sell": 1000000, "trust_net": 2000000,
     "dealer_buy": 2000000, "dealer_sell": 2500000, "dealer_net": -500000,
     "total_net": 13500000}
  ]
}
```

### 5.2 `GET /api/stocks/{stock_id}/margin`

參數同 5.1。

```json
{
  "stock_id": "2330", "name": "台積電", "market": "TWSE",
  "from": "2026-09-16", "to": "2026-09-18", "count": 1,
  "items": [
    {"time": "2026-09-18",
     "margin_buy": 1200000, "margin_sell": 900000, "margin_redeem": 100000,
     "margin_prev_balance": 20000000, "margin_balance": 20200000, "margin_limit": 100000000,
     "short_buy": 50000, "short_sell": 150000, "short_redeem": 10000,
     "short_prev_balance": 1000000, "short_balance": 1090000, "short_limit": 100000000,
     "offset_amount": 20000,
     "sbl_sell": 300000, "sbl_balance": 4500000,
     "margin_ratio": 5.396}
  ]
}
```

`margin_ratio`（資券比，%）＝ `short_balance ÷ margin_balance × 100`，四捨五入到小數第 3 位；`margin_balance` 為 0 時回 `null`。**在 API 層算，不落地。**

### 5.3 `GET /api/stocks/{stock_id}/foreign-holding`

參數同 5.1。上櫃個股一律 `count: 0`（M2 沒有上櫃來源）。

```json
{
  "stock_id": "2330", "name": "台積電", "market": "TWSE",
  "from": "2026-09-16", "to": "2026-09-18", "count": 1,
  "items": [
    {"time": "2026-09-18", "issued_shares": 25930380458, "holding_shares": 18151266320,
     "available_shares": 7779114138, "holding_ratio": 70.0, "available_ratio": 30.0,
     "limit_ratio": 100.0}
  ]
}
```

### 5.4 `GET /api/stocks/{stock_id}/shareholding`

參數：`from`、`to`（比對 `week_date`）、`limit`（1–520，預設 104 週）。

```json
{
  "stock_id": "2330", "name": "台積電", "market": "TWSE",
  "from": "2026-09-18", "to": "2026-09-18", "count": 1,
  "items": [
    {"week": "2026-09-18",
     "total_holders": 1000000, "total_shares": 1000000000,
     "big_holder_ratio": 80.0, "retail_ratio": 20.0,
     "levels": [
       {"level": 1, "holders": 600000, "shares": 50000000, "ratio": 5.0},
       {"level": 2, "holders": 350000, "shares": 100000000, "ratio": 10.0},
       {"level": 3, "holders": 40000, "shares": 50000000, "ratio": 5.0},
       {"level": 12, "holders": 5000, "shares": 100000000, "ratio": 10.0},
       {"level": 13, "holders": 2000, "shares": 100000000, "ratio": 10.0},
       {"level": 14, "holders": 1500, "shares": 100000000, "ratio": 10.0},
       {"level": 15, "holders": 1500, "shares": 500000000, "ratio": 50.0}
     ]}
  ]
}
```

- `levels` 只含 `level` 1–15，依 `level` 升冪；**16（合計）與 17（差異數調整）不放進 `levels`**。
- `total_holders` / `total_shares` 取 `level = 16` 那一列的 `holders` / `shares`；沒有 16 時改成 1–15 的總和。
- `big_holder_ratio` ＝ level 12–15 的 `ratio` 相加；`retail_ratio` ＝ level 1–4 的 `ratio` 相加。兩者都四捨五入到小數第 4 位（D-038）。

---

## T2-1　技術債：回補收進 CLI（U-9）、`daily_price` 索引（U-14）、備份腳本（U-12）

### 目標

把 M1 報告 §3.2 列的三個缺口清掉，讓 M2 後面的回補可以直接在 `twstock-etl` 映像裡跑。**本任務不碰任何籌碼邏輯。**

### 新增 / 修改檔案

```
db/migrations/versions/0003_daily_price_index.py   # 新增
etl/twstock_etl/cli.py                             # 改：加 backfill 子指令
etl/Dockerfile                                     # 改：加 COPY scripts
scripts/backfill.py                                # 改：改成薄包裝
scripts/backup.sh                                  # 新增
etl/tests/test_etl_backfill_cli.py                 # 新增
db/tests/test_db_migration_0003.py                 # 新增
```

**只准動上面 7 個檔案。**

### 1. Migration `0003_daily_price_index.py`

```python
revision: str = "0003"
down_revision: Union[str, None] = "0002"
```

```python
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
```

`db/twstock_db/tables.py` **不用改**（`Index` 物件不是必要的；M1 的 `ix_daily_price_trade_date` 也只在 migration 裡）。

### 2. `etl/twstock_etl/cli.py`：新增 `backfill` 子指令

在 `main()` 的 `subparsers` 裡加一個 `backfill` 子指令，它自己再有四個子子指令 `price` / `index` / `exright` / `calendar`，選項與目前 `scripts/backfill.py` **完全一致**：

```python
# backfill 子指令（U-9：讓回補可以在 twstock-etl 映像裡跑）
backfill_parser = subparsers.add_parser(
    "backfill",
    help="歷史資料回補（速率限制、斷點續傳、進度輸出）",
    epilog=BACKFILL_EPILOG,
    formatter_class=argparse.RawDescriptionHelpFormatter,
)
backfill_sub = backfill_parser.add_subparsers(dest="backfill_command", required=True)
```

- `BACKFILL_EPILOG`：把目前 `scripts/backfill.py` 的 `HELP_EPILOG` 原字串搬過來，並把裡面的 `scripts/backfill.py xxx` 改寫成 `python -m twstock_etl.cli backfill xxx`。
- 共用選項工廠 `_add_backfill_common_options(p)`：`--sleep`（float，預設 3.0）、`--force`、`--source-dir`（`Path`）、`--dry-run`、`--max-failures`（int，預設 10）。
- 四個子子指令的參數：
  - `price`：`--market {TWSE,TPEx}`（必填）、`--from` / `--to`（`YYYY-MM-DD`，用既有的 `_parse_date`，`dest` 分別為 `start` / `end`，必填）
  - `index`：`--from` / `--to`（`YYYY-MM` 字串，`dest` 為 `start` / `end`，必填）
  - `exright`：`--from` / `--to`（`YYYY-MM-DD`，必填）
  - `calendar`：`--from-year` / `--to-year`（int，必填）
- `main()` 的分派加一行 `elif args.command == "backfill": return _cmd_backfill(args)`。

```python
def _cmd_backfill(args: argparse.Namespace) -> int:
    """backfill 子指令實作；回傳碼 0 成功／1 有失敗／2 超過失敗上限／130 被 Ctrl-C 中斷。"""
```

實作要點（把目前 `scripts/backfill.py` 的 `main()` 後半段搬過來）：

1. `engine = get_engine()`（**不要**自己讀 `os.environ["DATABASE_URL"]`；`get_engine()` 讀不到會拋 `RuntimeError`，已被 `main()` 的 `except` 接住印 `error: …` 回 1）。
2. `options = BackfillOptions(sleep_seconds=args.sleep, max_failures=args.max_failures, force=args.force, source_dir=args.source_dir, dry_run=args.dry_run)`。
3. 依 `args.backfill_command` 呼叫 `backfill_prices` / `backfill_index` / `backfill_exright` / `backfill_calendar`。
4. 收尾（與現行 `scripts/backfill.py` 完全相同的語意）：
   - `summary.interrupted_at` 有值 → `print(f"已中斷，下次執行會從 {summary.interrupted_at} 繼續", file=sys.stderr)`；回 `130`
   - `summary.failed > 0` → 回 `1`
   - 否則回 `0`
   - `except BackfillAborted as exc` → `print(str(exc), file=sys.stderr)`；回 `2`
   - `except KeyboardInterrupt` → 回 `130`
5. `from twstock_etl.backfill import (BackfillAborted, BackfillOptions, backfill_calendar, backfill_exright, backfill_index, backfill_prices)` 放**模組頂層**，不要放函式內。

`main()` 現有的 `except (SourceFormatError, httpx.HTTPError, RuntimeError, FileNotFoundError)` 已經涵蓋 `backfill` 會丟的 `SourceFormatError` 與 `FileNotFoundError`，**不要再加一層**。

### 3. `etl/Dockerfile`：`scripts/` 進映像（U-9）

在 `COPY etl /app/etl` 之後加一行：

```dockerfile
COPY scripts /app/scripts
```

`.dockerignore` 不用改（裡面沒有排除 `scripts`）。

### 4. `scripts/backfill.py`：改成薄包裝

整支檔案換成下面這段（**不要保留任何 argparse 定義**）：

```python
#!/usr/bin/env python3
"""TwStock 歷史資料回補工具（保留相容用的薄包裝）。

真正的實作在 `python -m twstock_etl.cli backfill …`，這支只是把參數原樣轉過去，
讓 M1 時期寫下的指令與 README 範例繼續能用。用法見 `--help`。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "etl"))

from twstock_etl.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main(["backfill", *sys.argv[1:]]))
```

`scripts/m1_verify.sh` **不用改**（`scripts/backfill.py price …` 會被轉成 `backfill price …`，輸出與離開碼不變）。

### 5. `scripts/backup.sh`（U-12）

```bash
#!/usr/bin/env bash
# TwStock 資料庫備份。用法：scripts/backup.sh [備份目錄]（預設 data/backup）
# 需要環境變數 DATABASE_URL，格式 postgresql+psycopg://user:pass@host:port/dbname
set -euo pipefail
```

行為：

1. `DATABASE_URL` 未設定 → `echo "錯誤：未設定 DATABASE_URL" >&2; exit 1`。
2. 把 `postgresql+psycopg://` 前綴換成 `postgresql://`（`pg_dump` 不認 SQLAlchemy 的 driver 後綴）。
3. 備份目錄 `OUT_DIR="${1:-$ROOT/data/backup}"`，`mkdir -p`。
4. 檔名 `twstock_$(date +%Y%m%d_%H%M%S).dump`，指令：
   `pg_dump --format=custom --no-owner --no-privileges --file="$OUT_DIR/$NAME" "$PG_URL"`。
   `pg_dump` 找不到時（`command -v pg_dump` 失敗）改試 `/usr/lib/postgresql/16/bin/pg_dump`，再找不到 → `exit 1` 並印「找不到 pg_dump」。
5. 只保留最新 7 份：`ls -1t "$OUT_DIR"/twstock_*.dump | tail -n +8 | xargs -r rm -f`。
6. 成功時最後一行印 `BACKUP OK <完整路徑> <人類可讀大小>`，離開碼 0。
7. 檔頭註解要寫還原指令：
   `pg_restore --clean --if-exists --no-owner -d "$PG_URL" <dump 檔>`。

`chmod +x scripts/backup.sh`。**不要**把備份加進 `deploy/docker-compose.yml`，也不要加排程（D-032）。

### 6. 測試

`etl/tests/test_etl_backfill_cli.py`（不需要 DB，用 `monkeypatch` 把 `twstock_etl.cli` 裡的回補函式換成假的）：

1. `test_backfill_price_呼叫_backfill_prices_並帶對參數`：
   monkeypatch `twstock_etl.cli.get_engine` 回 `object()`、`twstock_etl.cli.backfill_prices` 換成記錄呼叫參數的假函式（回傳 `BackfillSummary(total=1, done=1, skipped=0, failed=0, rows=10)`）。
   呼叫 `main(["backfill", "price", "--market", "TWSE", "--from", "2026-09-16", "--to", "2026-09-18", "--sleep", "0", "--source-dir", "etl/tests/fixtures"])`。
   斷言：回傳 `0`；假函式收到的 `market == "TWSE"`、`start == date(2026, 9, 16)`、`end == date(2026, 9, 18)`、`options.sleep_seconds == 0.0`、`options.source_dir == Path("etl/tests/fixtures")`。
2. `test_backfill_有失敗回_1`：假函式回 `BackfillSummary(total=1, done=0, skipped=0, failed=1, rows=0)` → `main(...) == 1`。
3. `test_backfill_被中斷回_130`：假函式回的 summary 有 `interrupted_at="2026-09-17"` → `main(...) == 130`。
4. `test_backfill_超過失敗上限回_2`：假函式丟 `BackfillAborted("失敗次數超過 10，中止回補")` → `main(...) == 2`。
5. `test_backfill_index_子指令參數是年月字串`：`main(["backfill", "index", "--from", "2026-09", "--to", "2026-09", "--sleep", "0"])` → 假 `backfill_index` 收到 `start == "2026-09"`。

`db/tests/test_db_migration_0003.py`（需要 DB，用 `clean_db` fixture）：

1. `test_索引存在`：
   ```python
   rows = conn.execute(text(
       "SELECT indexdef FROM pg_indexes "
       "WHERE tablename = 'daily_price' AND indexname = 'ix_daily_price_stock_date_desc'"
   )).fetchall()
   assert len(rows) == 1
   assert "trade_date DESC" in rows[0][0]
   ```

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed（M1 的 216 passed 再加本任務新增的 6 個）；skipped 只有「此 PostgreSQL 未安裝 TimescaleDB…」那一筆

cd /home/claude/TwStock && export DATABASE_URL=$(TWSTOCK_PGDATA=/tmp/twstock-pg-t21 TWSTOCK_PGPORT=54341 scripts/pg_temp.sh reset) && \
  .venv/bin/alembic -c db/alembic.ini upgrade head && \
  .venv/bin/alembic -c db/alembic.ini downgrade 0002 && \
  .venv/bin/alembic -c db/alembic.ini upgrade head && echo REVERSIBLE_OK
# 預期：最後一行 REVERSIBLE_OK

cd /home/claude/TwStock && .venv/bin/python -m twstock_etl.cli backfill --help | head -3
# 預期：出現 "usage: ... backfill" 與四個子指令 price / index / exright / calendar

cd /home/claude/TwStock && scripts/m1_verify.sh | tail -1
# 預期：M1 VERIFY PASSED（薄包裝沒有改變任何行為）

cd /home/claude/TwStock && export DATABASE_URL=$(TWSTOCK_PGDATA=/tmp/twstock-pg-t21 TWSTOCK_PGPORT=54341 scripts/pg_temp.sh start) && \
  scripts/backup.sh /tmp/twstock-backup-test | tail -1
# 預期：BACKUP OK /tmp/twstock-backup-test/twstock_YYYYmmdd_HHMMSS.dump <大小>

cd /home/claude/TwStock && grep -c 'COPY scripts /app/scripts' etl/Dockerfile
# 預期：1

cd /home/claude/TwStock && docker compose -f deploy/docker-compose.yml --env-file .env.example config --quiet && echo COMPOSE_OK
# 預期：COMPOSE_OK
```

### 不要做的事

- 不要動 `etl/twstock_etl/backfill.py` 裡的回補邏輯（只是換一個進入點）。
- 不要動 `scripts/m1_verify.sh`。
- 不要改 `deploy/docker-compose.yml`（備份是手動腳本，不進 compose）。
- 不要建任何籌碼資料表或 parser（那是 T2-2 之後）。
- 不要順手升級任何 Python / npm 套件。
- 不要 `docker build` / `docker compose up`。

---

## T2-2　Migration 0004：籌碼四表與 `models.py` 五個 dataclass

### 目標

建立 §3 的四張籌碼表與對應的 ETL 資料模型。**本任務只碰 `db/` 與 `etl/twstock_etl/models.py`，不寫任何 parser / loader。**

### 新增 / 修改檔案

```
db/twstock_db/tables.py                       # 改：加 4 張表定義
db/migrations/versions/0004_chip_tables.py    # 新增
etl/twstock_etl/models.py                     # 改：加 5 個 dataclass
db/tests/test_db_chip_tables.py               # 新增
```

**只准動上面 4 個檔案。**

### 1. `db/twstock_db/tables.py`

在檔尾（`etl_job_log` 之後）依 §3 的 DDL 加四個 `Table`，風格完全比照既有的 `daily_price`：

- 型別對照：`VARCHAR(n)` → `String(n)`、`DATE` → `Date()`、`BIGINT` → `BigInteger()`、`SMALLINT` → `SmallInteger()`、`INTEGER` → `Integer()`、`NUMERIC(8,4)` → `Numeric(8, 4)`、`TIMESTAMPTZ` → `DateTime(timezone=True)`。
- `NOT NULL DEFAULT 0` → `nullable=False, server_default=text("0")`。
- `updated_at` → `nullable=False, server_default=func.now()`。
- `CHECK` → `CheckConstraint("…", name="…")`，名稱照 §3。
- 記得在 `from sqlalchemy import (...)` 補上 `SmallInteger`。

### 2. Migration `0004_chip_tables.py`

```python
revision: str = "0004"
down_revision: Union[str, None] = "0003"
```

`upgrade()`：依 §3 的順序 `op.create_table(...)` 建四張表、`op.create_index(...)` 建四個索引，最後：

```python
    conn = op.get_bind()
    create_hypertable_if_available(conn, "institutional_daily", "trade_date", "1 month")
    create_hypertable_if_available(conn, "margin_daily", "trade_date", "1 month")
    create_hypertable_if_available(conn, "foreign_holding", "trade_date", "1 month")
    create_hypertable_if_available(conn, "shareholding_dist", "week_date", "1 year")
```

`downgrade()`：反序 `op.drop_table("shareholding_dist")`、`"foreign_holding"`、`"margin_daily"`、`"institutional_daily"`。

寫法完全比照 `0002_price_tables.py`（含 `from twstock_db.timescale import create_hypertable_if_available`）。**沒有 `BIGSERIAL`，不需要 sequence 那段。**

### 3. `etl/twstock_etl/models.py`

在檔尾加五個 dataclass（全部 `@dataclass(frozen=True)`，欄位型別照 §3）：

```python
@dataclass(frozen=True)
class InstitutionalRecord:
    """三大法人買賣超紀錄（單位：股）。"""

    stock_id: str
    trade_date: date
    foreign_buy: int
    foreign_sell: int
    foreign_net: int
    trust_buy: int
    trust_sell: int
    trust_net: int
    dealer_buy: int
    dealer_sell: int
    dealer_net: int
    total_net: int
    source: str  # "TWSE" 或 "TPEx"


@dataclass(frozen=True)
class MarginRecord:
    """融資融券紀錄（單位：股）。"""

    stock_id: str
    trade_date: date
    margin_buy: int
    margin_sell: int
    margin_redeem: int
    margin_prev_balance: int
    margin_balance: int
    margin_limit: int | None
    short_buy: int
    short_sell: int
    short_redeem: int
    short_prev_balance: int
    short_balance: int
    short_limit: int | None
    offset_amount: int
    source: str


@dataclass(frozen=True)
class SblRecord:
    """借券賣出紀錄（單位：股），寫進 margin_daily 的 sbl_* 欄位。"""

    stock_id: str
    trade_date: date
    sbl_sell: int
    sbl_balance: int
    source: str = "TWSE"


@dataclass(frozen=True)
class ForeignHoldingRecord:
    """外資持股紀錄。"""

    stock_id: str
    trade_date: date
    issued_shares: int | None
    holding_shares: int
    available_shares: int | None
    holding_ratio: Decimal | None
    available_ratio: Decimal | None
    limit_ratio: Decimal | None
    source: str = "TWSE"


@dataclass(frozen=True)
class ShareholdingRecord:
    """集保股權分散單一級距紀錄。"""

    stock_id: str
    week_date: date
    level: int  # 1–17
    holders: int
    shares: int
    ratio: Decimal
```

### 4. 測試（`db/tests/test_db_chip_tables.py`，需要 DB，用 `clean_db` fixture）

1. `test_四張表都建起來`：查 `information_schema.tables`，`institutional_daily`、`margin_daily`、`foreign_holding`、`shareholding_dist` 都在。
2. `test_institutional_daily_欄位與型別`：查 `information_schema.columns`，斷言 `foreign_net` 是 `bigint` 且 `is_nullable = 'NO'`、`source` 是 `character varying`、`updated_at` 有 `column_default`。
3. `test_shareholding_dist_主鍵三欄`：查 `information_schema.key_column_usage`，主鍵欄位集合 == `{"stock_id", "week_date", "level"}`。
4. `test_level_check_擋住_0_與_18`：插一列 `level=0` 要拋 `IntegrityError`；`level=18` 也要拋；`level=17` 成功。（用 `pytest.raises(IntegrityError)`，每次用獨立的 `engine.begin()` 區塊避免交易汙染。）
5. `test_margin_daily_source_check`：`source='OTHER'` 要拋 `IntegrityError`；`'TPEx'` 成功。
6. `test_可以_upsert_同一個主鍵`：對 `institutional_daily` 用 `pg_insert(...).on_conflict_do_update(index_elements=["stock_id","trade_date"], set_={"foreign_net": ...})` 寫兩次，最後 `foreign_net` 是第二次的值，且總列數為 1。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed；skipped 只有 TimescaleDB 那一筆

cd /home/claude/TwStock && export DATABASE_URL=$(TWSTOCK_PGDATA=/tmp/twstock-pg-t22 TWSTOCK_PGPORT=54342 scripts/pg_temp.sh reset) && \
  .venv/bin/alembic -c db/alembic.ini upgrade head && \
  .venv/bin/alembic -c db/alembic.ini downgrade base && \
  .venv/bin/alembic -c db/alembic.ini upgrade head && echo REVERSIBLE_OK
# 預期：最後一行 REVERSIBLE_OK；中途出現四行「未安裝 TimescaleDB，… 維持一般資料表」

cd /home/claude/TwStock && /usr/lib/postgresql/16/bin/psql "$(echo $DATABASE_URL | sed 's|postgresql+psycopg|postgresql|')" -c '\d shareholding_dist'
# 預期：欄位與 §3 DDL 逐欄一致（含 ck_shareholding_dist_level 與 ix_shareholding_dist_week）

cd /home/claude/TwStock && scripts/m1_verify.sh | tail -1
# 預期：M1 VERIFY PASSED（回歸）
```

### 不要做的事

- 不要寫任何 parser、loader、job、CLI、排程、API、前端。
- 不要動 M1 的四張表或 `0002_price_tables.py`。
- 不要在 `models.py` 動既有的六個 dataclass。
- 不要為籌碼表加外鍵（沿用 D-017：由 loader 以 `stock` 表過濾未知代號）。

---

## T2-3　集保股權分散（TDCC）端到端：parser → loader → job → CLI → 每週排程

### 目標

讓「每週抓一次集保股權分散」這條路整條打通。**本任務通過審查後，使用者就可以在 Mac 上啟動排程開始累積歷史，不必等 M2 做完**（§0.1）。官方只留最新一週，所以這裡沒有回補、也不會有回補。

### 新增 / 修改檔案

```
etl/twstock_etl/sources/tdcc.py                    # 新增
etl/twstock_etl/loaders/shareholding.py            # 新增
etl/twstock_etl/loaders/job_log.py                 # 改：JobRun 加 target 欄位與 set_target()
etl/twstock_etl/jobs.py                            # 改：加 ShareholdingJobResult + load_shareholding
etl/twstock_etl/cli.py                             # 改：加 load-shareholding 子指令
etl/twstock_etl/scheduler.py                       # 改：加 run_shareholding_job 與週末排程
etl/tests/fixtures/tdcc_shareholding_20260918.csv  # 新增
etl/tests/test_etl_tdcc.py                         # 新增
etl/tests/test_etl_shareholding.py                 # 新增
etl/tests/test_etl_job_log.py                      # 改：加 set_target 測試
etl/tests/test_etl_cli.py                          # 改：加 load-shareholding 測試
etl/tests/test_etl_scheduler.py                    # 改：加集保排程測試
```

**只准動上面 12 個檔案。**

### 1. Fixture `etl/tests/fixtures/tdcc_shareholding_20260918.csv`

UTF-8、**不加 BOM**、逗號分隔、LF 換行。內容**逐字**如下（26 筆資料 + 1 列表頭；`2330` 的 `16` 那列故意用引號包千分位，用來驗證 `clean_cell` 有作用；`9999` 不在 `stock` 表，用來驗證未知代號過濾）：

```csv
資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%
20260918,2330,1,600000,50000000,5.00
20260918,2330,2,350000,100000000,10.00
20260918,2330,3,40000,50000000,5.00
20260918,2330,12,5000,100000000,10.00
20260918,2330,13,2000,100000000,10.00
20260918,2330,14,1500,100000000,10.00
20260918,2330,15,1500,500000000,50.00
20260918,2330,16,"1,000,000","1,000,000,000",100.00
20260918,1101,1,150000,20000000,4.00
20260918,1101,2,40000,30000000,6.00
20260918,1101,3,8000,25000000,5.00
20260918,1101,12,1200,50000000,10.00
20260918,1101,13,500,75000000,15.00
20260918,1101,14,200,50000000,10.00
20260918,1101,15,100,250000000,50.00
20260918,1101,16,200000,500000000,100.00
20260918,3105,1,60000,8000000,4.00
20260918,3105,2,15000,12000000,6.00
20260918,3105,3,3000,10000000,5.00
20260918,3105,12,1200,20000000,10.00
20260918,3105,13,500,30000000,15.00
20260918,3105,14,200,20000000,10.00
20260918,3105,15,100,100000000,50.00
20260918,3105,16,80000,200000000,100.00
20260918,9999,1,100,1000,0.10
20260918,9999,16,100,1000000,100.00
```

> 真實資料每檔有 1–15 級距加 16（合計），部分資料集還有 17（差異數調整），共約 2,000 檔 × 17 列。這份 fixture 只留 1/2/3/12/13/14/15/16 八級做精簡樣本，**parser 不得要求級距完整**。

### 2. `etl/twstock_etl/sources/tdcc.py`

```python
"""集保股權分散（TDCC 開放資料）parser。"""

TDCC_URL = "https://opendata.tdcc.com.tw/getOD.ashx"
TDCC_DATASET_ID = "1-5"
TDCC_HEADER_FIELDS = ("資料日期", "證券代號", "持股分級", "人數", "股數", "占集保庫存數比例")


def fetch_tdcc_shareholding(client: httpx.Client | None = None) -> str:
    """下載集保股權分散 CSV 原文（UTF-8 字串）。"""


def parse_tdcc_shareholding(text: str) -> list[ShareholdingRecord]:
    """把集保股權分散 CSV 轉成 ShareholdingRecord 清單。

    Raises:
        SourceFormatError: 表頭缺欄位、或解析結果為空
    """
```

`fetch_tdcc_shareholding` 實作要點（比照 M1 `twse_price.fetch_twse_daily` 的 client 開關寫法）：
用 `get_with_retry(client, TDCC_URL, params={"id": TDCC_DATASET_ID})`，回傳 `response.text`；`client is None` 時自己 `default_client()` 並在 `finally` 關掉。

`parse_tdcc_shareholding` 實作要點：

1. `text = text.lstrip("﻿")`（有些下載會帶 BOM）。
2. `rows = list(csv.reader(io.StringIO(text)))`；空的或只有表頭 → `raise SourceFormatError("集保股權分散 CSV 沒有資料列")`。
3. 表頭 `header = [clean_cell(c) for c in rows[0]]`，用 M1 既有的 `find_field(header, "資料日期")` 等六次取得索引（比例欄用 `find_field(header, "占集保庫存數比例")`，靠 `find_field` 的前綴比對吃掉結尾的 `%`）。找不到會由 `find_field` 拋 `SourceFormatError`。
4. 逐列（`rows[1:]`）：
   - 欄位數少於表頭 → `logger.debug` 後 `continue`。
   - `stock_id = clean_cell(row[i_code])`；不符 `^[0-9A-Z]{4,6}$` → `logger.debug` 後 `continue`。
   - `week_date = _parse_tdcc_date(clean_cell(row[i_date]))`；`None` → `logger.debug` 後 `continue`。
   - `level = parse_int(row[i_level])`；`None` 或不在 `1 <= level <= 17` → `logger.warning("略過不支援的持股分級 %r", …)` 後 `continue`。
   - `holders = parse_int(row[i_holders]) or 0`、`shares = parse_int(row[i_shares]) or 0`。
   - `ratio = (parse_decimal(row[i_ratio]) or Decimal(0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)`。
5. 結果為空 → `raise SourceFormatError("集保股權分散解析結果為空")`。

```python
def _parse_tdcc_date(value: str) -> date | None:
    """解析集保資料日期；不認得回 None。

    直接包 M1 既有的 `twstock_etl.dates.parse_tw_date`（已支援 'YYYYMMDD'、
    'YYYY/MM/DD'、民國格式），只是把 ValueError 轉成 None。**不要自己寫第二套日期解析。**
    """
```

### 3. `etl/twstock_etl/loaders/job_log.py`：`JobRun` 加 `set_target()`（D-033）

`JobRun` 改成：

```python
@dataclass
class JobRun:
    """一次 job 執行的可變狀態，由 job_run() yield 出來。"""

    job_id: int
    job_name: str
    rows: int = 0  # 呼叫端執行完把筆數寫回來
    note: str | None = None  # 跳過原因，寫進 error 欄位
    target_date: date | None = None
    target_key: str | None = None
    engine: Engine | None = None  # 由 job_run() 填入，供 set_target() 用

    def skip(self, reason: str) -> NoReturn:
        """中止此次 job 並記為 skipped。"""
        raise JobSkipped(reason)

    def set_target(
        self, *, target_date: date | None = None, target_key: str | None = None
    ) -> None:
        """在 job 執行中補記 target_date / target_key。

        給「目標要解析完資料才知道」的 job 用（例如集保只有最新一週，
        週五日期寫在檔案裡）。會立刻 UPDATE etl_job_log 那一列。

        Raises:
            RuntimeError: 這個 JobRun 沒有 engine
        """
```

`job_run()` 建立 `JobRun` 時改成 `JobRun(job_id=job_id, job_name=job_name, target_date=target_date, target_key=target_key, engine=engine)`；其餘邏輯（success / skipped / failed 三條路徑）**一個字都不要改**。

`set_target` 實作：`engine is None` → `raise RuntimeError("JobRun 沒有 engine，無法補記 target")`；否則設好 `self.target_date` / `self.target_key`，再用獨立交易 `engine.begin()` 執行 `etl_job_log.update().where(etl_job_log.c.job_id == self.job_id).values(target_date=..., target_key=...)`。

### 4. `etl/twstock_etl/loaders/shareholding.py`

```python
"""集保股權分散寫入 loader。"""

from twstock_etl.loaders.price import PriceUpsertResult, known_stock_ids  # 重用，不要複製一份


def upsert_shareholding(
    conn: Connection, records: Sequence[ShareholdingRecord]
) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, week_date, level) DO UPDATE 寫入；stock 表沒有的代號略過。"""
```

邏輯**完全比照** `loaders/price.py` 的 `upsert_daily_prices`：

- `records` 為空 → 回 `PriceUpsertResult(written=0, skipped_unknown=0)`。
- 用 `known_stock_ids(conn)` 過濾；未知代號收進 `unknown_ids` 集合，`logger.info("略過 %d 筆不在 stock 表的代號：%s", …)`（只印前 5 個）。
- 同批主鍵 `(stock_id, week_date, level)` 去重保留最後一筆。
- 每 `BATCH_SIZE = 1000` 一批 `pg_insert(shareholding_dist).values(rows).on_conflict_do_update(index_elements=["stock_id", "week_date", "level"], set_={"holders": …, "shares": …, "ratio": …, "updated_at": func.now()})`。
- 回 `PriceUpsertResult(written=總筆數, skipped_unknown=len(unknown_ids))`。

### 5. `etl/twstock_etl/jobs.py`

新增（放在 `load_adj_factors` 之後）：

```python
@dataclass(frozen=True)
class ShareholdingJobResult:
    """集保股權分散載入結果。"""

    week_date: date | None
    rows: int
    skipped_unknown: int
    skip_reason: str | None = None


def load_shareholding(
    engine: Engine,
    *,
    csv_text: str | None = None,
    client: httpx.Client | None = None,
    force: bool = False,
) -> ShareholdingJobResult:
    """抓（或用傳入的）集保股權分散 CSV 並寫入 shareholding_dist，全程記 etl_job_log。

    官方只保留最新一週，所以沒有日期參數，也沒有回補；target_date 由資料裡的
    「資料日期」決定（D-033）。

    Returns:
        ShareholdingJobResult；被略過時 rows=0、skipped_unknown=0、skip_reason 為略過原因
    """
```

函式主體（**照抄結構，只能有一個 `return`**）：

```python
    job_name = "shareholding_tdcc"
    week_date: date | None = None
    rows = 0
    skipped_unknown = 0

    with job_run(engine, job_name) as run:
        if csv_text is None:
            csv_text = fetch_tdcc_shareholding(client)

        records = parse_tdcc_shareholding(csv_text)
        week_date = max(r.week_date for r in records)
        run.set_target(target_date=week_date)

        with engine.begin() as conn:
            if not force and has_successful_run(conn, job_name, target_date=week_date):
                run.skip("已完成，略過")

        latest = [r for r in records if r.week_date == week_date]
        with engine.begin() as conn:
            upsert_result = upsert_shareholding(conn, latest)
        rows = upsert_result.written
        skipped_unknown = upsert_result.skipped_unknown
        run.rows = rows

    return ShareholdingJobResult(
        week_date=week_date,
        rows=rows,
        skipped_unknown=skipped_unknown,
        skip_reason=run.note,
    )
```

import 加在檔案頂層：`from twstock_etl.loaders.shareholding import upsert_shareholding`、`from twstock_etl.sources.tdcc import fetch_tdcc_shareholding, parse_tdcc_shareholding`。

### 6. `etl/twstock_etl/cli.py`：`load-shareholding` 子指令

```
load-shareholding [--file PATH] [--force]
```

- `--file`：本機 CSV 檔案路徑（UTF-8），用 `args.file.read_text(encoding="utf-8")` 讀成 `csv_text`。
- `--force`：跳過斷點續傳檢查。
- `_cmd_load_shareholding(args)` 輸出（與 §4 的 job 名稱一致）：

| 情況 | 輸出（一行） |
| --- | --- |
| 正常載入 | `loaded shareholding week=2026-09-18 rows=24 skipped_unknown=1` |
| 被略過 | `skipped shareholding week=2026-09-18 reason=已完成，略過` |

`week=` 用 `result.week_date.isoformat()`；`week_date` 為 `None`（理論上不會發生）時印 `week=-`。一律回 `0`。

### 7. `etl/twstock_etl/scheduler.py`

```python
def run_shareholding_job(engine: Engine) -> None:
    """抓集保股權分散（官方只留最新一週，漏抓補不回來）；失敗只記 log。"""
    try:
        _log_job_outcome("集保股權分散", load_shareholding(engine))
    except Exception:
        logger.exception("載入集保股權分散失敗")
```

在 `build_scheduler()` 裡註冊（放在除權除息那段之後）：

```python
    # 集保股權分散：每週六、日 10:00 與 16:00 台北時間各試一次
    # （官方只留最新一週，漏抓補不回來，所以一週排四次；同一週靠 etl_job_log 去重）
    scheduler.add_job(
        run_shareholding_job,
        trigger=CronTrigger(day_of_week="sat,sun", hour="10,16", minute=0, timezone=TAIPEI),
        args=[engine],
        id="shareholding_tdcc",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=21600,
    )
```

頂層 import 補 `load_shareholding`。

### 8. 測試

`etl/tests/test_etl_tdcc.py`（不需要 DB）：

1. `test_解析_fixture_得到_26_筆`：讀 fixture → `len(records) == 26`。
2. `test_2330_level_15_的數值`：找 `stock_id="2330" and level=15` → `holders == 1500`、`shares == 500_000_000`、`ratio == Decimal("50.0000")`、`week_date == date(2026, 9, 18)`。
3. `test_千分位被清掉`：`2330` 的 `level=16` → `holders == 1_000_000`、`shares == 1_000_000_000`。
4. `test_未知代號也會被解析出來`：`9999` 有 2 筆（過濾是 loader 的事，不是 parser 的事）。
5. `test_表頭缺欄位拋_SourceFormatError`：把表頭的「持股分級」改成「XX」→ `pytest.raises(SourceFormatError)`。
6. `test_只有表頭拋_SourceFormatError`。
7. `test_級距_0_與_18_被略過`：自組兩列 `level=0`、`level=18` 加一列合法 → 只回 1 筆。
8. `test_日期兩種寫法都認得`：`20260918` 與 `2026/09/18` 都解析成 `date(2026, 9, 18)`。

`etl/tests/test_etl_shareholding.py`（需要 DB，用 `clean_db` fixture；先 `upsert_stocks` 塞 `2330`／`1101`／`3105` 三檔，**不要**塞 `9999`）：

1. `test_upsert_寫入_24_筆_未知代號_1`：`upsert_shareholding(conn, parse(fixture))` → `written == 24`、`skipped_unknown == 1`。
2. `test_重跑同一份資料不會變成_48_筆`：連跑兩次，`SELECT count(*) FROM shareholding_dist` == 24。
3. `test_load_shareholding_寫_etl_job_log_的_target_date`：`load_shareholding(engine, csv_text=fixture)` → 結果 `week_date == date(2026, 9, 18)`、`rows == 24`、`skip_reason is None`；查 `etl_job_log` 最後一列 `job_name == "shareholding_tdcc"`、`status == "success"`、`target_date == date(2026, 9, 18)`、`rows == 24`。
4. `test_第二次呼叫會_skip`：再呼叫一次 → `rows == 0`、`skip_reason == "已完成，略過"`；`etl_job_log` 多一列 `status == "skipped"` 且 `target_date == date(2026, 9, 18)`。
5. `test_force_可以重跑`：`force=True` → `rows == 24`、`skip_reason is None`。
6. `test_parser_失敗記成_failed`：`csv_text="資料日期\n"` → `pytest.raises(SourceFormatError)`，且 `etl_job_log` 最後一列 `status == "failed"`、`error` 非空。

`etl/tests/test_etl_job_log.py` 加（需要 DB）：

7. `test_set_target_會更新_etl_job_log`：`with job_run(engine, "shareholding_tdcc") as run: run.set_target(target_date=date(2026, 9, 18))` → 該列 `target_date == date(2026, 9, 18)`、`status == "success"`。
8. `test_set_target_沒有_engine_拋_RuntimeError`：手動建 `JobRun(job_id=1, job_name="x")` → `pytest.raises(RuntimeError)`。

`etl/tests/test_etl_cli.py` 加：

9. `test_load_shareholding_輸出格式`：monkeypatch `twstock_etl.cli.get_engine` 與 `twstock_etl.cli.load_shareholding`（回 `ShareholdingJobResult(week_date=date(2026,9,18), rows=24, skipped_unknown=1)`），`main(["load-shareholding", "--file", "etl/tests/fixtures/tdcc_shareholding_20260918.csv"])` → capsys 輸出剛好是 `loaded shareholding week=2026-09-18 rows=24 skipped_unknown=1\n`，回 `0`。
10. `test_load_shareholding_skip_輸出格式`：假函式回 `skip_reason="已完成，略過"`、`rows=0` → 輸出 `skipped shareholding week=2026-09-18 reason=已完成，略過\n`。

`etl/tests/test_etl_scheduler.py` 加：

11. `test_build_scheduler_有集保_job`：`build_scheduler(engine).get_job("shareholding_tdcc")` 不是 `None`，且 `str(job.trigger)` 含 `sat` 與 `sun`。
12. `test_run_shareholding_job_略過時記_info_不記_exception`：monkeypatch `twstock_etl.scheduler.load_shareholding` 回 `skip_reason="已完成，略過"` 的結果 → `caplog` 內有 `略過`，且沒有 `ERROR` 等級的紀錄。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed；skipped 只有 TimescaleDB 那一筆

cd /home/claude/TwStock && export DATABASE_URL=$(TWSTOCK_PGDATA=/tmp/twstock-pg-t23 TWSTOCK_PGPORT=54343 scripts/pg_temp.sh reset) && \
  .venv/bin/alembic -c db/alembic.ini upgrade head >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TPEx --file etl/tests/fixtures/isin_tpex_strmode4.html >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-shareholding --file etl/tests/fixtures/tdcc_shareholding_20260918.csv && \
  .venv/bin/python -m twstock_etl.cli load-shareholding --file etl/tests/fixtures/tdcc_shareholding_20260918.csv
# 預期（兩行，exit 0）：
# loaded shareholding week=2026-09-18 rows=24 skipped_unknown=1
# skipped shareholding week=2026-09-18 reason=已完成，略過

cd /home/claude/TwStock && /usr/lib/postgresql/16/bin/psql "$(echo $DATABASE_URL | sed 's|postgresql+psycopg|postgresql|')" \
  -c "SELECT sum(ratio) FROM shareholding_dist WHERE stock_id='2330' AND level BETWEEN 12 AND 15"
# 預期：80.0000

cd /home/claude/TwStock && /usr/lib/postgresql/16/bin/psql "$(echo $DATABASE_URL | sed 's|postgresql+psycopg|postgresql|')" \
  -c "SELECT job_name, status, target_date, rows FROM etl_job_log WHERE job_name='shareholding_tdcc' ORDER BY job_id"
# 預期兩列：success / 2026-09-18 / 24，skipped / 2026-09-18 / 0

cd /home/claude/TwStock && scripts/m1_verify.sh | tail -1
# 預期：M1 VERIFY PASSED（回歸）
```

### 不要做的事

- **不要**寫集保的回補子指令（官方只留最新一週，回補不存在；`backfill` 也不要新增 `shareholding`）。
- 不要動 `job_run()` 的 success / skipped / failed 三條路徑，只加 `JobRun` 的欄位與 `set_target()`。
- 不要在 `jobs.py` 動 M1 的任何既有函式。
- 不要用 `pandas` 讀 CSV（標準庫 `csv` 就夠，且映像沒有 pandas）。
- 不要寫任何法人／融資券／借券／外資持股的程式（T2-4 之後）。
- 不要寫 API 或前端。

---

## T2-4　來源 parser：三大法人（上市 T86、上櫃含舊版備援）

### 目標

把 S1 / S2 / S3 三個端點的回應轉成 `InstitutionalRecord`。**本任務只寫 parser 與 fixture，不碰 DB、不碰 job。**

### 新增 / 修改檔案

```
etl/twstock_etl/sources/report.py                   # 改：新增 find_field_all()
etl/twstock_etl/sources/institutional.py            # 新增（上市 + 上櫃都放這支）
etl/tests/fixtures/TWSE_institutional_20260916.json # 新增
etl/tests/fixtures/TWSE_institutional_20260917.json # 新增
etl/tests/fixtures/TWSE_institutional_20260918.json # 新增
etl/tests/fixtures/TPEx_institutional_20260918.json # 新增
etl/tests/fixtures/TPEx_institutional_legacy_sample.json  # 新增
etl/tests/test_etl_report_fields.py                 # 新增（find_field_all 單元測試）
etl/tests/test_etl_institutional.py                 # 新增
```

**只准動上面 8 個檔案。**

### 1. `sources/report.py` 新增 `find_field_all()`

M1 的 `find_field` 只能「完全相符或前綴相符」，法人報表的欄位名是
`外陸資買進股數(不含外資自營商)`（上市）vs `外資及陸資(不含外資自營商)買進股數`（上櫃），
關鍵字位置不同，前綴比對會抓錯欄位。新增一個「必須同時包含所有關鍵字」的找法：

```python
def find_field_all(
    fields: Sequence[str],
    *tokens: str,
    exclude: Sequence[str] = (),
) -> int:
    """回傳第一個「同時包含 tokens 全部關鍵字、且不含 exclude 任一關鍵字」的欄位索引。

    Args:
        fields: 欄位名稱清單
        tokens: 必須全部出現在欄位名稱裡的關鍵字
        exclude: 只要出現任一個就排除該欄位

    Raises:
        SourceFormatError: 找不到
    """


def find_field_all_optional(
    fields: Sequence[str], *tokens: str, exclude: Sequence[str] = ()
) -> int | None:
    """同 find_field_all，但找不到時回 None（給「舊格式沒有這一欄」的情況用）。"""
```

比對前先把每個欄位名 `clean_cell` 一次（去 HTML 標籤與全形空白），再做 `in` 判斷。
**不要改 `find_field`、`extract_table`、`is_no_trade` 的任何行為**，M1 的 parser 還在用。

### 2. `sources/institutional.py`

```python
"""三大法人買賣超 parser（上市 T86、上櫃 dailyTrade，含舊版備援）。"""

TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
TPEX_INST_URL = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
TPEX_INST_URL_LEGACY = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"

# 舊版備援端點只回 aaData、沒有 fields，欄位靠固定順序（順序來源：官方報表欄位標題列）
TPEX_LEGACY_INST_FIELDS = (
    "代號", "名稱",
    "外資及陸資(不含外資自營商)買進股數", "外資及陸資(不含外資自營商)賣出股數",
    "外資及陸資(不含外資自營商)買賣超股數",
    "外資自營商買進股數", "外資自營商賣出股數", "外資自營商買賣超股數",
    "外資及陸資買進股數", "外資及陸資賣出股數", "外資及陸資買賣超股數",
    "投信買進股數", "投信賣出股數", "投信買賣超股數",
    "自營商(自行買賣)買進股數", "自營商(自行買賣)賣出股數", "自營商(自行買賣)買賣超股數",
    "自營商(避險)買進股數", "自營商(避險)賣出股數", "自營商(避險)買賣超股數",
    "自營商買進股數", "自營商賣出股數", "自營商買賣超股數",
    "三大法人買賣超股數",
)

# extract_table 用來認表的必要欄位（上市／上櫃共用，用 find_field 的前綴比對找得到即可）
INSTITUTIONAL_REQUIRED_FIELDS = ("投信買進股數", "投信賣出股數", "三大法人買賣超股數")


def fetch_twse_institutional(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上市三大法人買賣超 JSON。"""


def fetch_tpex_institutional(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上櫃三大法人買賣超 JSON；新版端點失敗時自動退回舊版端點。"""


def parse_twse_institutional(payload: dict, trade_date: date) -> list[InstitutionalRecord]:
    """把上市三大法人 JSON 轉成 InstitutionalRecord 清單（source="TWSE"）。"""


def parse_tpex_institutional(payload: dict, trade_date: date) -> list[InstitutionalRecord]:
    """把上櫃三大法人 JSON 轉成 InstitutionalRecord 清單（source="TPEx"）。"""


def _parse_institutional_table(
    fields: Sequence[str], data: Sequence[Sequence[object]], trade_date: date, source: str
) -> list[InstitutionalRecord]:
    """上市／上櫃共用的法人表格解析。"""
```

- `fetch_twse_institutional`：`params = {"date": trade_date.strftime("%Y%m%d"), "selectType": "ALL", "response": "json"}`，寫法比照 M1 `twse_price.fetch_twse_daily`（含 `client is None` 時自建 + `finally` 關閉）。
- `fetch_tpex_institutional`：寫法**完全比照** M1 `tpex_price.fetch_tpex_daily` 的備援結構——
  先試 `TPEX_INST_URL`（`params={"type": "Daily", "sect": "EW", "date": trade_date.strftime("%Y/%m/%d"), "response": "json"}`），
  用 `extract_table(payload, INSTITUTIONAL_REQUIRED_FIELDS)` 試解析確認可用；
  `httpx.HTTPError` / `ValueError` / `SourceFormatError` 任一 → `logger.warning("新版 TPEx 法人端點失敗（%s），改用舊版", …)` 後改打
  `TPEX_INST_URL_LEGACY`（`params={"l": "zh-tw", "se": "EW", "t": "D", "d": f"{trade_date.year - 1911}/{trade_date:%m/%d}", "o": "json"}`）。
- `parse_tpex_institutional` 先判形狀：`"aaData" in payload and "fields" not in payload` → `fields = list(TPEX_LEGACY_INST_FIELDS)`、`data = payload["aaData"]`（空的就拋 `SourceFormatError("上櫃法人舊版資料表為空")`）；否則 `fields, data = extract_table(payload, INSTITUTIONAL_REQUIRED_FIELDS)`。
- `parse_twse_institutional` 一律走 `extract_table(payload, INSTITUTIONAL_REQUIRED_FIELDS)`。
- 兩個 parse 都**不要**比對 payload 裡的日期（T86 的 `date` 欄格式與 M1 不同，比對只會製造假失敗）；`trade_date` 以參數為準。

#### 2.1 欄位查找表（`_parse_institutional_table` 用，照抄）

| 變數 | 主要查法 | 找不到時的備援 | 必要？ |
| --- | --- | --- | --- |
| `i_f_buy` | `find_field_all(fields, "買進", "不含外資自營商")` | `find_field_all(fields, "外資", "買進", exclude=("自營商",))` | 必要 |
| `i_f_sell` | `find_field_all(fields, "賣出", "不含外資自營商")` | `find_field_all(fields, "外資", "賣出", exclude=("自營商",))` | 必要 |
| `i_fd_buy` | `find_field_all_optional(fields, "外資自營商", "買進")` | — | 可缺（缺＝0） |
| `i_fd_sell` | `find_field_all_optional(fields, "外資自營商", "賣出")` | — | 可缺（缺＝0） |
| `i_t_buy` | `find_field_all(fields, "投信", "買進")` | — | 必要 |
| `i_t_sell` | `find_field_all(fields, "投信", "賣出")` | — | 必要 |
| `i_ds_buy` | `find_field_all_optional(fields, "自營商", "自行買賣", "買進")` | `find_field_all(fields, "自營商", "買進", exclude=("外資", "避險"))` | 必要 |
| `i_ds_sell` | `find_field_all_optional(fields, "自營商", "自行買賣", "賣出")` | `find_field_all(fields, "自營商", "賣出", exclude=("外資", "避險"))` | 必要 |
| `i_dh_buy` | `find_field_all_optional(fields, "自營商", "避險", "買進")` | — | 可缺（缺＝0） |
| `i_dh_sell` | `find_field_all_optional(fields, "自營商", "避險", "賣出")` | — | 可缺（缺＝0） |
| `i_total` | `find_field_all_optional(fields, "三大法人", "買賣超")` | — | 可缺（缺＝自行相加） |
| `i_code` | `find_field(fields, "證券代號", "代號", "股票代號")` | — | 必要 |

「主要查法」用 optional 版時，**先試主要、為 `None` 再用備援**（備援仍然用會拋例外的 `find_field_all`）。

#### 2.2 每一列的計算（照抄）

```python
    for row in data:
        stock_id = clean_cell(row[i_code])
        if not stock_id or not re.match(r"^[0-9A-Z]{4,6}$", stock_id):
            logger.debug("跳過無效代號：%r", stock_id)
            continue

        def cell(index: int | None) -> int:
            return 0 if index is None else (parse_int(row[index]) or 0)

        foreign_buy = cell(i_f_buy) + cell(i_fd_buy)
        foreign_sell = cell(i_f_sell) + cell(i_fd_sell)
        trust_buy = cell(i_t_buy)
        trust_sell = cell(i_t_sell)
        dealer_buy = cell(i_ds_buy) + cell(i_dh_buy)
        dealer_sell = cell(i_ds_sell) + cell(i_dh_sell)
        foreign_net = foreign_buy - foreign_sell
        trust_net = trust_buy - trust_sell
        dealer_net = dealer_buy - dealer_sell
        total_net = (
            parse_int(row[i_total]) if i_total is not None else None
        )
        if total_net is None:
            total_net = foreign_net + trust_net + dealer_net
```

- 買賣超一律**自己用買進減賣出算**，不讀官方的買賣超欄（官方欄位有時是空白或含符號）；`total_net` 則存官方原值供核對（D-035）。
- 解析結果為空 → `raise SourceFormatError(f"{trade_date} {source} 三大法人解析結果為空")`。
- `source` 由呼叫端傳入（`"TWSE"` / `"TPEx"`）。

### 3. Fixture

#### 3.1 `TWSE_institutional_20260918.json`（**逐字照抄**，其他兩天照 §3.2 改數字）

```json
{
  "stat": "OK",
  "date": "20260918",
  "title": "115年09月18日 三大法人買賣超日報",
  "fields": ["證券代號", "證券名稱", "外陸資買進股數(不含外資自營商)", "外陸資賣出股數(不含外資自營商)", "外陸資買賣超股數(不含外資自營商)", "外資自營商買進股數", "外資自營商賣出股數", "外資自營商買賣超股數", "投信買進股數", "投信賣出股數", "投信買賣超股數", "自營商買賣超股數", "自營商買進股數(自行買賣)", "自營商賣出股數(自行買賣)", "自營商買賣超股數(自行買賣)", "自營商買進股數(避險)", "自營商賣出股數(避險)", "自營商買賣超股數(避險)", "三大法人買賣超股數"],
  "data": [
    ["2330", "台積電", "28,000,000", "17,000,000", "11,000,000", "2,000,000", "1,000,000", "1,000,000", "3,000,000", "1,000,000", "2,000,000", "-500,000", "1,200,000", "1,500,000", "-300,000", "800,000", "1,000,000", "-200,000", "13,500,000"],
    ["1101", "台泥", "1,000,000", "800,000", "200,000", "0", "0", "0", "100,000", "50,000", "50,000", "-10,000", "20,000", "25,000", "-5,000", "10,000", "15,000", "-5,000", "240,000"],
    ["2317", "鴻海", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
    ["9999", "測試不存在", "1,000", "0", "1,000", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "1,000"]
  ],
  "notes": []
}
```

#### 3.2 `TWSE_institutional_20260916.json` / `…_20260917.json`

同樣的 `fields` 與四列代號（`2330`／`1101`／`2317`／`9999`），只有 `date`、`title` 與 `2330` 那列的數字不同；`1101`、`2317`、`9999` 三列**與 20260918 完全相同**。`2330` 的數字：

| 日期 | 外陸資買/賣/超 | 外資自營商買/賣/超 | 投信買/賣/超 | 自營自行買/賣/超 | 自營避險買/賣/超 | 自營商買賣超 | 三大法人買賣超 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-16 | 12,000,000 / 8,000,000 / 4,000,000 | 2,000,000 / 1,000,000 / 1,000,000 | 2,000,000 / 1,000,000 / 1,000,000 | 500,000 / 600,000 / -100,000 | 300,000 / 500,000 / -200,000 | -300,000 | 5,700,000 |
| 2026-09-17 | 20,000,000 / 12,000,000 / 8,000,000 | 1,000,000 / 1,000,000 / 0 | 1,000,000 / 3,000,000 / -2,000,000 | 1,000,000 / 900,000 / 100,000 | 400,000 / 300,000 / 100,000 | 200,000 | 6,200,000 |
| 2026-09-18 | 28,000,000 / 17,000,000 / 11,000,000 | 2,000,000 / 1,000,000 / 1,000,000 | 3,000,000 / 1,000,000 / 2,000,000 | 1,200,000 / 1,500,000 / -300,000 | 800,000 / 1,000,000 / -200,000 | -500,000 | 13,500,000 |

換算成 `InstitutionalRecord`（Coder 可以用來自我檢查）：

| 日期 | foreign_buy | foreign_sell | foreign_net | trust_net | dealer_buy | dealer_sell | dealer_net | total_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-16 | 14,000,000 | 9,000,000 | **5,000,000** | 1,000,000 | 800,000 | 1,100,000 | -300,000 | 5,700,000 |
| 2026-09-17 | 21,000,000 | 13,000,000 | **8,000,000** | -2,000,000 | 1,400,000 | 1,200,000 | 200,000 | 6,200,000 |
| 2026-09-18 | 30,000,000 | 18,000,000 | **12,000,000** | 2,000,000 | 2,000,000 | 2,500,000 | -500,000 | 13,500,000 |

（外資三天都是買超，M2 的「外資連買天數」驗收會用到這組數字。）

#### 3.3 `TPEx_institutional_20260918.json`（`tables` 信封，欄位名與上市不同）

```json
{
  "stat": "OK",
  "date": "2026/09/18",
  "tables": [
    {
      "title": "上櫃股票三大法人買賣超日報",
      "fields": ["代號", "名稱", "外資及陸資(不含外資自營商)買進股數", "外資及陸資(不含外資自營商)賣出股數", "外資及陸資(不含外資自營商)買賣超股數", "外資自營商買進股數", "外資自營商賣出股數", "外資自營商買賣超股數", "投信買進股數", "投信賣出股數", "投信買賣超股數", "自營商(自行買賣)買進股數", "自營商(自行買賣)賣出股數", "自營商(自行買賣)買賣超股數", "自營商(避險)買進股數", "自營商(避險)賣出股數", "自營商(避險)買賣超股數", "自營商買賣超股數", "三大法人買賣超股數"],
      "data": [
        ["3105", "穩懋", "2,000,000", "1,500,000", "500,000", "100,000", "50,000", "50,000", "200,000", "100,000", "100,000", "50,000", "80,000", "-30,000", "20,000", "10,000", "10,000", "-20,000", "630,000"],
        ["8069", "元太", "1,000,000", "1,200,000", "-200,000", "0", "0", "0", "50,000", "20,000", "30,000", "10,000", "5,000", "5,000", "0", "0", "0", "5,000", "-165,000"],
        ["9999", "測試不存在", "1,000", "0", "1,000", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "1,000"]
      ],
      "notes": []
    }
  ]
}
```

換算：`3105` → foreign_buy 2,100,000 / foreign_sell 1,550,000 / **foreign_net 550,000**、trust_net 100,000、dealer_buy 70,000 / dealer_sell 90,000 / **dealer_net -20,000**、total_net 630,000。

#### 3.4 `TPEx_institutional_legacy_sample.json`（舊版備援形狀，沒有 `fields`）

```json
{
  "reportDate": "115/09/18",
  "aaData": [
    ["3105", "穩懋", "2,000,000", "1,500,000", "500,000", "100,000", "50,000", "50,000", "2,100,000", "1,550,000", "550,000", "200,000", "100,000", "100,000", "50,000", "80,000", "-30,000", "20,000", "10,000", "10,000", "70,000", "90,000", "-20,000", "630,000"]
  ]
}
```

（24 欄，順序對應 `TPEX_LEGACY_INST_FIELDS`。解析結果要與 §3.3 的 `3105` **完全相同**。）

### 4. 測試

`etl/tests/test_etl_report_fields.py`（不需要 DB）：

1. `test_find_field_all_全部關鍵字都要命中`：`find_field_all(["外陸資買進股數(不含外資自營商)", "外資自營商買進股數"], "買進", "不含外資自營商") == 0`。
2. `test_find_field_all_exclude_排除欄位`：`find_field_all(["外資自營商買進股數", "自營商買進股數(自行買賣)"], "自營商", "買進", exclude=("外資",)) == 1`。
3. `test_find_field_all_找不到拋_SourceFormatError`。
4. `test_find_field_all_optional_找不到回_None`。
5. `test_欄位名含_HTML_標籤也找得到`：`find_field_all(["<b>投信買進股數</b>"], "投信", "買進") == 0`。

`etl/tests/test_etl_institutional.py`（不需要 DB，直接讀 fixture）：

6. `test_上市解析四筆`：`len(records) == 4`（未知代號的過濾是 loader 的事）。
7. `test_上市_2330_三天的數值`：對 09-16 / 09-17 / 09-18 三個 fixture，逐一比對 §3.2 第二張表的 8 個欄位。
8. `test_上市_2317_全零也會被收`：`2317` 在結果裡，且所有數值為 0。
9. `test_上櫃新版解析三筆與_3105_數值`：比對 §3.3 的換算值，`source == "TPEx"`。
10. `test_上櫃舊版備援解析結果與新版一致`：用 `TPEx_institutional_legacy_sample.json` 解析出的 `3105` 記錄，與 §3.3 解析出的 `3105` 記錄**逐欄相等**。
11. `test_缺少投信欄位拋_SourceFormatError`：把 fixture 的 `fields` 裡「投信買進股數」改名成 `XX` → `pytest.raises(SourceFormatError)`。
12. `test_data_為空拋_SourceFormatError`。
13. `test_fetch_上櫃新版失敗會退回舊版`：用 `httpx.MockTransport` 讓新版端點回 500、舊版端點回 `TPEx_institutional_legacy_sample.json` 的內容，`fetch_tpex_institutional(date(2026, 9, 18), client)` 要回傳含 `aaData` 的 payload，且 `caplog` 有 warning。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed；skipped 只有 TimescaleDB 那一筆

cd /home/claude/TwStock && .venv/bin/python -c "
import json
from datetime import date
from twstock_etl.sources.institutional import parse_twse_institutional, parse_tpex_institutional
tw = parse_twse_institutional(json.load(open('etl/tests/fixtures/TWSE_institutional_20260918.json')), date(2026,9,18))
tp = parse_tpex_institutional(json.load(open('etl/tests/fixtures/TPEx_institutional_20260918.json')), date(2026,9,18))
r = [x for x in tw if x.stock_id=='2330'][0]
print('twse', len(tw), r.foreign_buy, r.foreign_sell, r.foreign_net, r.trust_net, r.dealer_net, r.total_net)
s = [x for x in tp if x.stock_id=='3105'][0]
print('tpex', len(tp), s.foreign_net, s.trust_net, s.dealer_net, s.total_net, s.source)
"
# 預期輸出：
# twse 4 30000000 18000000 12000000 2000000 -500000 13500000
# tpex 3 550000 100000 -20000 630000 TPEx
```

### 不要做的事

- 不要改 `find_field` / `extract_table` / `is_no_trade` 既有行為（M1 的 parser 還在用）。
- 不要寫 loader、job、CLI、排程、API、前端。
- 不要建資料表、不要寫 migration。
- 不要讀官方買賣超欄位當作 `*_net`（一律買進減賣出）。
- 不要在 parser 裡比對 payload 的日期欄。
- 不要加任何新套件。

---

## T2-5　來源 parser：融資融券（上市／上櫃）、借券賣出（上市）、外資持股（上市）

### 目標

把 S4 ～ S8 五個端點的回應轉成 `MarginRecord` / `SblRecord` / `ForeignHoldingRecord`。
**本任務只寫 parser 與 fixture，不碰 DB、不碰 job。**

### 新增 / 修改檔案

```
etl/twstock_etl/sources/margin.py                    # 新增（上市 + 上櫃融資融券）
etl/twstock_etl/sources/twse_sbl.py                  # 新增（借券賣出）
etl/twstock_etl/sources/twse_foreign.py              # 新增（外資持股）
etl/tests/fixtures/TWSE_margin_20260916.json         # 新增
etl/tests/fixtures/TWSE_margin_20260917.json         # 新增
etl/tests/fixtures/TWSE_margin_20260918.json         # 新增
etl/tests/fixtures/TPEx_margin_20260918.json         # 新增
etl/tests/fixtures/TPEx_margin_legacy_sample.json    # 新增
etl/tests/fixtures/TWSE_sbl_20260918.json            # 新增
etl/tests/fixtures/TWSE_foreign_20260918.json        # 新增
etl/tests/test_etl_margin.py                         # 新增
etl/tests/test_etl_sbl_foreign.py                    # 新增
```

**只准動上面 13 個檔案。**

### 1. 單位換算（D-036，最重要的一條）

```python
# 融資融券報表的數量單位是「交易單位（張）」，本專案一律存「股」，所以 ×1000。
# 借券（S7）與外資持股（S8）本來就是「股」，不換算。
SHARES_PER_LOT = 1000
```

`margin.py` 的兩個 parser 對**所有股數欄位**（含 `margin_limit` / `short_limit`）都乘 `SHARES_PER_LOT`；
`twse_sbl.py` 與 `twse_foreign.py` **不乘**。
這條是本里程碑最可能被真實資料打臉的假設，已列入 §7 的 V-13 專門驗證。

### 2. `sources/margin.py`

```python
"""融資融券 parser（上市 MI_MARGN、上櫃 margin/balance，含舊版備援）。"""

TWSE_MARGIN_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
TPEX_MARGIN_URL = "https://www.tpex.org.tw/www/zh-tw/margin/balance"
TPEX_MARGIN_URL_LEGACY = "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php"

TWSE_MARGIN_REQUIRED_FIELDS = ("股票代號", "融資今日餘額", "融券今日餘額")
TPEX_MARGIN_REQUIRED_FIELDS = ("代號", "資餘額", "券餘額")

TPEX_LEGACY_MARGIN_FIELDS = (
    "代號", "名稱", "前資餘額(張)", "資買", "資賣", "現償", "資餘額", "資屬證金",
    "資使用率(%)", "資限額", "前券餘額(張)", "券賣", "券買", "券償", "券餘額",
    "券屬證金", "券使用率(%)", "券限額", "資券相抵", "備註",
)

SHARES_PER_LOT = 1000


def fetch_twse_margin(trade_date: date, client: httpx.Client | None = None) -> dict: ...
def fetch_tpex_margin(trade_date: date, client: httpx.Client | None = None) -> dict: ...
def parse_twse_margin(payload: dict, trade_date: date) -> list[MarginRecord]: ...
def parse_tpex_margin(payload: dict, trade_date: date) -> list[MarginRecord]: ...
```

- `fetch_twse_margin`：`params = {"date": trade_date.strftime("%Y%m%d"), "selectType": "ALL", "response": "json"}`，寫法比照 `twse_price.fetch_twse_daily`。
- `fetch_tpex_margin`：備援結構**完全比照** `tpex_price.fetch_tpex_daily`——新版 `params={"date": trade_date.strftime("%Y/%m/%d"), "response": "json"}`，用 `extract_table(payload, TPEX_MARGIN_REQUIRED_FIELDS)` 試解析；失敗 → `logger.warning` 後打舊版 `params={"l": "zh-tw", "d": f"{trade_date.year - 1911}/{trade_date:%m/%d}", "o": "json"}`。
- `parse_twse_margin`：`fields, data = extract_table(payload, TWSE_MARGIN_REQUIRED_FIELDS)`（MI_MARGN 是多表信封，`extract_table` 會自己挑到含「股票代號」的那張）。
- `parse_tpex_margin`：`"aaData" in payload and "fields" not in payload` → 用 `TPEX_LEGACY_MARGIN_FIELDS`；否則 `extract_table(payload, TPEX_MARGIN_REQUIRED_FIELDS)`。
- 兩者都**不比對** payload 的日期欄；`trade_date` 以參數為準。
- 代號檢查同 T2-4：`^[0-9A-Z]{4,6}$`，不符就 `logger.debug` 後 `continue`。
- 解析結果為空 → `SourceFormatError(f"{trade_date} {source} 融資融券解析結果為空")`。

#### 2.1 欄位查找表（上市，`parse_twse_margin`）

| 目標欄位 | 查法 | 必要？ |
| --- | --- | --- |
| `stock_id` | `find_field(fields, "股票代號", "證券代號", "代號")` | 必要 |
| `margin_buy` | `find_field_all(fields, "融資", "買進")` | 必要 |
| `margin_sell` | `find_field_all(fields, "融資", "賣出")` | 必要 |
| `margin_redeem` | `find_field_all(fields, "現金償還")` | 必要 |
| `margin_prev_balance` | `find_field_all(fields, "融資", "前日餘額")` | 必要 |
| `margin_balance` | `find_field_all(fields, "融資", "今日餘額")` | 必要 |
| `margin_limit` | `find_field_all_optional(fields, "融資", "限額")` | 可缺 |
| `short_buy` | `find_field_all(fields, "融券", "買進")` | 必要 |
| `short_sell` | `find_field_all(fields, "融券", "賣出")` | 必要 |
| `short_redeem` | `find_field_all(fields, "現券償還")` | 必要 |
| `short_prev_balance` | `find_field_all(fields, "融券", "前日餘額")` | 必要 |
| `short_balance` | `find_field_all(fields, "融券", "今日餘額")` | 必要 |
| `short_limit` | `find_field_all_optional(fields, "融券", "限額")` | 可缺 |
| `offset_amount` | `find_field_all_optional(fields, "資券互抵")` | 可缺（缺＝0） |

#### 2.2 欄位查找表（上櫃，`parse_tpex_margin`）

| 目標欄位 | 查法 | 必要？ |
| --- | --- | --- |
| `stock_id` | `find_field(fields, "代號", "股票代號", "證券代號")` | 必要 |
| `margin_prev_balance` | `find_field_all(fields, "前資餘額")` | 必要 |
| `margin_buy` | `find_field_all(fields, "資買")` | 必要 |
| `margin_sell` | `find_field_all(fields, "資賣")` | 必要 |
| `margin_redeem` | `find_field_all(fields, "現償")` | 必要 |
| `margin_balance` | `find_field_all(fields, "資餘額", exclude=("前",))` | 必要 |
| `margin_limit` | `find_field_all_optional(fields, "資限額")` | 可缺 |
| `short_prev_balance` | `find_field_all(fields, "前券餘額")` | 必要 |
| `short_sell` | `find_field_all(fields, "券賣")` | 必要 |
| `short_buy` | `find_field_all(fields, "券買")` | 必要 |
| `short_redeem` | `find_field_all(fields, "券償")` | 必要 |
| `short_balance` | `find_field_all(fields, "券餘額", exclude=("前",))` | 必要 |
| `short_limit` | `find_field_all_optional(fields, "券限額")` | 可缺 |
| `offset_amount` | `find_field_all_optional(fields, "資券相抵")`，`None` 時再試 `find_field_all_optional(fields, "資券互抵")` | 可缺（缺＝0） |

#### 2.3 取值規則（兩個 parser 共用，照抄）

```python
        def lots(index: int | None) -> int:
            """張 → 股；欄位不存在或空值一律 0。"""
            return 0 if index is None else (parse_int(row[index]) or 0) * SHARES_PER_LOT

        def lots_optional(index: int | None) -> int | None:
            """張 → 股；欄位不存在或是 '-' / 空白時回 None（限額欄用）。"""
            if index is None:
                return None
            value = parse_int(row[index])
            return None if value is None else value * SHARES_PER_LOT
```

`margin_limit` / `short_limit` 用 `lots_optional`，其餘全部用 `lots`。`source` 由呼叫端決定（`"TWSE"` / `"TPEx"`）。

### 3. `sources/twse_sbl.py`

```python
"""借券賣出餘額 parser（上市 TWT93U）。單位是股，不做張→股換算。"""

TWSE_SBL_URL = "https://www.twse.com.tw/rwd/zh/SBL/TWT93U"
TWSE_SBL_REQUIRED_FIELDS = ("股票代號", "借券賣出當日餘額")


def fetch_twse_sbl(trade_date: date, client: httpx.Client | None = None) -> dict:
    """下載指定日期的上市借券賣出餘額 JSON。"""


def parse_twse_sbl(payload: dict, trade_date: date) -> list[SblRecord]:
    """把借券賣出餘額 JSON 轉成 SblRecord 清單（source="TWSE"）。"""
```

- `params = {"date": trade_date.strftime("%Y%m%d"), "response": "json"}`。
- `fields, data = extract_table(payload, TWSE_SBL_REQUIRED_FIELDS)`。
- 查找：`stock_id` = `find_field(fields, "股票代號", "證券代號", "代號")`；
  `sbl_sell` = `find_field_all(fields, "當日賣出")`；
  `sbl_balance` = `find_field_all(fields, "當日餘額")`。
- 數值 `parse_int(...) or 0`，**不乘 1000**。
- 代號檢查、空結果拋 `SourceFormatError` 同前。

### 4. `sources/twse_foreign.py`

```python
"""外資持股 parser（上市 MI_QFIIS）。"""

TWSE_QFIIS_URL = "https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS"
TWSE_QFIIS_REQUIRED_FIELDS = ("證券代號", "發行股數", "全體外資及陸資持股股數")


def fetch_twse_foreign_holding(trade_date: date, client: httpx.Client | None = None) -> dict: ...
def parse_twse_foreign_holding(payload: dict, trade_date: date) -> list[ForeignHoldingRecord]: ...
```

- `params = {"date": trade_date.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"}`。
- 查找：`stock_id` = `find_field(fields, "證券代號", "股票代號", "代號")`；
  `issued_shares` = `find_field_all_optional(fields, "發行股數")`；
  `available_shares` = `find_field_all_optional(fields, "尚可投資股數")`；
  `holding_shares` = `find_field_all(fields, "持股股數")`；
  `available_ratio` = `find_field_all_optional(fields, "尚可投資比率")`；
  `holding_ratio` = `find_field_all_optional(fields, "持股比率")`；
  `limit_ratio` = `find_field_all_optional(fields, "上限比率")`。
- 股數用 `parse_int`（`holding_shares` 為 `None` 時填 0，其餘保留 `None`）；
  比率用 `parse_decimal(...)`，非 `None` 時 `.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)`。
- 不乘 1000。

### 5. Fixture

#### 5.1 `TWSE_margin_20260918.json`（**逐字照抄**；數字單位是「張」）

```json
{
  "stat": "OK",
  "date": "20260918",
  "title": "115年09月18日 融資融券彙總",
  "tables": [
    {
      "title": "信用交易統計",
      "fields": ["項目", "買進", "賣出", "現金(券)償還", "前日餘額", "今日餘額"],
      "data": [["融資(交易單位)", "150,000", "140,000", "5,000", "3,000,000", "3,005,000"]],
      "notes": []
    },
    {
      "title": "融資融券彙總",
      "fields": ["股票代號", "股票名稱", "融資買進", "融資賣出", "現金償還", "融資前日餘額", "融資今日餘額", "融資限額", "融券買進", "融券賣出", "現券償還", "融券前日餘額", "融券今日餘額", "融券限額", "資券互抵", "註記"],
      "data": [
        ["2330", "台積電", "1,200", "900", "100", "20,000", "20,200", "100,000", "50", "150", "10", "1,000", "1,090", "100,000", "20", ""],
        ["1101", "台泥", "100", "80", "0", "5,000", "5,020", "50,000", "5", "10", "0", "100", "105", "50,000", "2", ""],
        ["0050", "元大台灣50", "10", "5", "0", "300", "305", "-", "0", "0", "0", "0", "0", "-", "0", ""],
        ["9999", "測試不存在", "1", "0", "0", "10", "11", "1,000", "0", "0", "0", "0", "0", "1,000", "0", ""]
      ],
      "notes": []
    }
  ]
}
```

`2330` 解析後（單位股）：`margin_buy 1,200,000`、`margin_sell 900,000`、`margin_redeem 100,000`、
`margin_prev_balance 20,000,000`、`margin_balance 20,200,000`、`margin_limit 100,000,000`、
`short_buy 50,000`、`short_sell 150,000`、`short_redeem 10,000`、`short_prev_balance 1,000,000`、
`short_balance 1,090,000`、`short_limit 100,000,000`、`offset_amount 20,000`。
`0050` 的 `margin_limit` 與 `short_limit` 都是 **`None`**（原值 `-`）。

#### 5.2 `TWSE_margin_20260916.json` / `…_20260917.json`

`fields` 與四列代號同 §5.1，`1101` / `0050` / `9999` 三列數值不變，只改 `2330`（單位張）：

| 日期 | 融資買/賣/現償/前日/今日/限額 | 融券買/賣/現償/前日/今日/限額 | 資券互抵 |
| --- | --- | --- | --- |
| 2026-09-16 | 1,000 / 700 / 50 / 19,250 / 19,500 / 100,000 | 30 / 100 / 5 / 835 / 900 / 100,000 | 10 |
| 2026-09-17 | 1,100 / 500 / 100 / 19,500 / 20,000 / 100,000 | 40 / 160 / 20 / 900 / 1,000 / 100,000 | 15 |

→ `margin_balance` 三天分別是 **19,500,000 / 20,000,000 / 20,200,000** 股，
`short_balance` 三天分別是 **900,000 / 1,000,000 / 1,090,000** 股（M2 驗收會用到）。

#### 5.3 `TPEx_margin_20260918.json`

```json
{
  "stat": "OK",
  "date": "2026/09/18",
  "tables": [
    {
      "title": "上櫃股票融資融券餘額",
      "fields": ["代號", "名稱", "前資餘額(張)", "資買", "資賣", "現償", "資餘額", "資屬證金", "資使用率(%)", "資限額", "前券餘額(張)", "券賣", "券買", "券償", "券餘額", "券屬證金", "券使用率(%)", "券限額", "資券相抵", "備註"],
      "data": [
        ["3105", "穩懋", "3,000", "200", "100", "0", "3,100", "0", "3.10", "100,000", "200", "50", "20", "0", "230", "0", "0.23", "100,000", "5", ""],
        ["8069", "元太", "1,500", "100", "50", "0", "1,550", "0", "1.55", "80,000", "100", "10", "5", "0", "105", "0", "0.11", "80,000", "1", ""],
        ["9999", "測試不存在", "10", "1", "0", "0", "11", "0", "0.01", "1,000", "0", "0", "0", "0", "0", "0", "0.00", "1,000", "0", ""]
      ],
      "notes": []
    }
  ]
}
```

`3105` 解析後（單位股）：`margin_prev_balance 3,000,000`、`margin_buy 200,000`、`margin_sell 100,000`、
`margin_redeem 0`、`margin_balance 3,100,000`、`margin_limit 100,000,000`、
`short_prev_balance 200,000`、`short_sell 50,000`、`short_buy 20,000`、`short_redeem 0`、
`short_balance 230,000`、`short_limit 100,000,000`、`offset_amount 5,000`、`source == "TPEx"`。
（`資使用率(%)`、`資屬證金`、`券屬證金`、`券使用率(%)`、`備註` 五欄**不解析、不入庫**。）

#### 5.4 `TPEx_margin_legacy_sample.json`

```json
{
  "reportDate": "115/09/18",
  "aaData": [
    ["3105", "穩懋", "3,000", "200", "100", "0", "3,100", "0", "3.10", "100,000", "200", "50", "20", "0", "230", "0", "0.23", "100,000", "5", ""]
  ]
}
```

（20 欄，順序對應 `TPEX_LEGACY_MARGIN_FIELDS`；解析結果要與 §5.3 的 `3105` **逐欄相同**。）

#### 5.5 `TWSE_sbl_20260918.json`（單位股）

```json
{
  "stat": "OK",
  "date": "20260918",
  "title": "115年09月18日 借券賣出餘額",
  "fields": ["股票代號", "股票名稱", "借券賣出前日餘額", "借券賣出當日賣出", "借券賣出當日還券", "借券賣出當日調整", "借券賣出當日餘額", "次一營業日可限額"],
  "data": [
    ["2330", "台積電", "4,350,000", "300,000", "150,000", "0", "4,500,000", "500,000,000"],
    ["1101", "台泥", "100,000", "10,000", "5,000", "0", "105,000", "50,000,000"],
    ["9999", "測試不存在", "1,000", "100", "0", "0", "1,100", "1,000,000"]
  ],
  "notes": []
}
```

`2330` → `sbl_sell 300,000`、`sbl_balance 4,500,000`。

#### 5.6 `TWSE_foreign_20260918.json`（單位股 / %）

```json
{
  "stat": "OK",
  "date": "20260918",
  "title": "115年09月18日 外資及陸資投資持股統計",
  "fields": ["證券代號", "證券名稱", "發行股數", "外資及陸資尚可投資股數", "全體外資及陸資持股股數", "外資及陸資尚可投資比率", "全體外資及陸資持股比率", "法令投資上限比率"],
  "data": [
    ["2330", "台積電", "25,930,380,458", "7,779,114,138", "18,151,266,320", "30.00", "70.00", "100.00"],
    ["1101", "台泥", "5,000,000,000", "4,000,000,000", "1,000,000,000", "80.00", "20.00", "100.00"],
    ["9999", "測試不存在", "1,000,000", "900,000", "100,000", "90.00", "10.00", "100.00"]
  ],
  "notes": []
}
```

`2330` → `issued_shares 25,930,380,458`、`available_shares 7,779,114,138`、
`holding_shares 18,151,266,320`、`available_ratio Decimal("30.0000")`、
`holding_ratio Decimal("70.0000")`、`limit_ratio Decimal("100.0000")`。

### 6. 測試

`etl/tests/test_etl_margin.py`（不需要 DB）：

1. `test_上市解析四筆`（含 `9999`）。
2. `test_上市_2330_三天的餘額`：三個 fixture 的 `margin_balance` 依序 19,500,000 / 20,000,000 / 20,200,000，`short_balance` 依序 900,000 / 1,000,000 / 1,090,000。
3. `test_上市_2330_20260918_十三個欄位`：逐欄比對 §5.1 的換算值。
4. `test_限額為破折號時是_None`：`0050` 的 `margin_limit is None and short_limit is None`。
5. `test_上櫃新版解析三筆與_3105_數值`：比對 §5.3，`source == "TPEx"`。
6. `test_上櫃舊版備援與新版結果逐欄相同`。
7. `test_缺必要欄位拋_SourceFormatError`：把上市 fixture 第二張表的「融資今日餘額」改名 → `pytest.raises(SourceFormatError)`。
8. `test_fetch_上櫃新版失敗會退回舊版`：`httpx.MockTransport`，新版 500、舊版回 §5.4 內容，`caplog` 有 warning。
9. `test_上市信用交易統計那張表不會被誤選`：解析結果裡沒有「項目」欄造成的假紀錄（`len(records) == 4`，且 `records[0].stock_id == "2330"`）。

`etl/tests/test_etl_sbl_foreign.py`（不需要 DB）：

10. `test_借券解析三筆與_2330_數值`：`sbl_sell == 300_000`、`sbl_balance == 4_500_000`、`source == "TWSE"`。
11. `test_借券不做張轉股`：`1101` 的 `sbl_balance == 105_000`（不是 105,000,000）。
12. `test_外資持股_2330_六個欄位`：逐欄比對 §5.6，比率是 `Decimal` 且為 4 位小數。
13. `test_外資持股缺上限比率欄也能解析`：刪掉 `法令投資上限比率` 欄與對應值 → `limit_ratio is None`，其他欄正常。
14. `test_兩者空表都拋_SourceFormatError`。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed；skipped 只有 TimescaleDB 那一筆

cd /home/claude/TwStock && .venv/bin/python -c "
import json
from datetime import date
from twstock_etl.sources.margin import parse_twse_margin, parse_tpex_margin
from twstock_etl.sources.twse_sbl import parse_twse_sbl
from twstock_etl.sources.twse_foreign import parse_twse_foreign_holding
f = lambda n: json.load(open('etl/tests/fixtures/'+n))
m = [x for x in parse_twse_margin(f('TWSE_margin_20260918.json'), date(2026,9,18)) if x.stock_id=='2330'][0]
print('twse-margin', m.margin_balance, m.short_balance, m.margin_limit, m.offset_amount)
t = [x for x in parse_tpex_margin(f('TPEx_margin_20260918.json'), date(2026,9,18)) if x.stock_id=='3105'][0]
print('tpex-margin', t.margin_balance, t.short_balance, t.source)
s = [x for x in parse_twse_sbl(f('TWSE_sbl_20260918.json'), date(2026,9,18)) if x.stock_id=='2330'][0]
print('sbl', s.sbl_sell, s.sbl_balance)
q = [x for x in parse_twse_foreign_holding(f('TWSE_foreign_20260918.json'), date(2026,9,18)) if x.stock_id=='2330'][0]
print('foreign', q.holding_shares, q.holding_ratio, q.available_ratio)
"
# 預期輸出：
# twse-margin 20200000 1090000 100000000 20000
# tpex-margin 3100000 230000 TPEx
# sbl 300000 4500000
# foreign 18151266320 70.0000 30.0000
```

### 不要做的事

- 不要把借券或外資持股的股數乘 1000（只有融資融券要乘）。
- 不要寫 loader、job、CLI、排程、API、前端。
- 不要動 T2-4 的 `institutional.py` 或 `report.py`。
- 不要在 parser 裡比對 payload 的日期欄。
- 不要做上櫃借券、上櫃外資持股（不在 M2 範圍，D-029）。
- 不要加任何新套件。

---

## T2-6　Loader、來源登錄表、統一 job／CLI／排程／回補

### 目標

把 T2-4、T2-5 的六個 parser 接上資料庫：寫入三張表、一個泛用 job、一個 CLI 子指令、六個排程項、一個回補子指令。
**關鍵設計（D-034）：不要為每一類籌碼各寫一份 job／CLI／排程**，全部走同一個「來源登錄表」。

### 新增 / 修改檔案

```
etl/twstock_etl/loaders/chip.py        # 新增（四個 upsert）
etl/twstock_etl/chip_sources.py        # 新增（來源登錄表）
etl/twstock_etl/jobs.py                # 改：加 ChipJobResult + load_chip_daily
etl/twstock_etl/cli.py                 # 改：加 load-chip 與 backfill chip
etl/twstock_etl/scheduler.py           # 改：加 run_chip_job 與六個排程項
etl/twstock_etl/backfill.py            # 改：加 backfill_chip
etl/tests/test_etl_chip_loaders.py     # 新增
etl/tests/test_etl_chip_jobs.py        # 新增
etl/tests/test_etl_chip_backfill.py    # 新增
etl/tests/test_etl_cli.py              # 改
etl/tests/test_etl_scheduler.py        # 改
```

**只准動上面 11 個檔案。**

### 1. `loaders/chip.py`

```python
"""籌碼三表寫入 loader。"""

from twstock_etl.loaders.price import PriceUpsertResult, known_stock_ids  # 重用


def upsert_institutional(conn: Connection, records: Sequence[InstitutionalRecord]) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, trade_date) DO UPDATE 寫入 institutional_daily。"""


def upsert_margin(conn: Connection, records: Sequence[MarginRecord]) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, trade_date) DO UPDATE 寫入 margin_daily 的融資融券欄位。"""


def upsert_sbl(conn: Connection, records: Sequence[SblRecord]) -> PriceUpsertResult:
    """把借券資料寫進 margin_daily 的 sbl_* 兩欄；不碰融資融券欄位（D-037）。"""


def upsert_foreign_holding(conn: Connection, records: Sequence[ForeignHoldingRecord]) -> PriceUpsertResult:
    """以 ON CONFLICT (stock_id, trade_date) DO UPDATE 寫入 foreign_holding。"""
```

四個函式的骨架**完全比照** `loaders/price.py` 的 `upsert_daily_prices`：
未知代號用 `known_stock_ids(conn)` 過濾並 `logger.info`、同批主鍵去重保留最後一筆、
`BATCH_SIZE = 1000` 分批、回 `PriceUpsertResult(written=…, skipped_unknown=len(unknown_ids))`。

`on_conflict_do_update` 的 `set_` 內容：

| 函式 | `set_` 要更新的欄位 |
| --- | --- |
| `upsert_institutional` | `foreign_buy`、`foreign_sell`、`foreign_net`、`trust_buy`、`trust_sell`、`trust_net`、`dealer_buy`、`dealer_sell`、`dealer_net`、`total_net`、`source`、`updated_at=func.now()` |
| `upsert_margin` | `margin_buy`、`margin_sell`、`margin_redeem`、`margin_prev_balance`、`margin_balance`、`margin_limit`、`short_buy`、`short_sell`、`short_redeem`、`short_prev_balance`、`short_balance`、`short_limit`、`offset_amount`、`source`、`updated_at=func.now()`（**不要動 `sbl_sell` / `sbl_balance`**） |
| `upsert_sbl` | **只有** `sbl_sell`、`sbl_balance`、`updated_at=func.now()`（**不要動 `source`，也不要動任何融資融券欄位**） |
| `upsert_foreign_holding` | `issued_shares`、`holding_shares`、`available_shares`、`holding_ratio`、`available_ratio`、`limit_ratio`、`source`、`updated_at=func.now()` |

`upsert_sbl` 的 INSERT 欄位只有 `stock_id`、`trade_date`、`sbl_sell`、`sbl_balance`、`source`——
其餘 `NOT NULL` 欄位靠 DDL 的 `DEFAULT 0`。這代表**借券可以先於融資融券寫入**，之後融資融券再補上，兩邊都不會互相覆蓋。

### 2. `chip_sources.py`（D-034）

```python
"""籌碼來源登錄表：把 kind × market 對應到 fetch / parse / upsert 與 job 名稱。"""

@dataclass(frozen=True)
class ChipSource:
    """一個籌碼來源（一種資料 × 一個市場）。"""

    kind: str       # institutional / margin / sbl / foreign
    market: str     # TWSE / TPEx
    job_name: str   # 見規格 §4
    label: str      # 中文說明，給 log 與 CLI 用，例「上市三大法人」
    fetch: Callable[[date, httpx.Client | None], dict]
    parse: Callable[[dict, date], list]
    upsert: Callable[[Connection, Sequence], PriceUpsertResult]


CHIP_KINDS: tuple[str, ...] = ("institutional", "margin", "sbl", "foreign")

CHIP_SOURCES: dict[tuple[str, str], ChipSource] = {
    ("institutional", "TWSE"): ChipSource("institutional", "TWSE", "institutional_twse", "上市三大法人",
                                          fetch_twse_institutional, parse_twse_institutional, upsert_institutional),
    ("institutional", "TPEx"): ChipSource("institutional", "TPEx", "institutional_tpex", "上櫃三大法人",
                                          fetch_tpex_institutional, parse_tpex_institutional, upsert_institutional),
    ("margin", "TWSE"):        ChipSource("margin", "TWSE", "margin_twse", "上市融資融券",
                                          fetch_twse_margin, parse_twse_margin, upsert_margin),
    ("margin", "TPEx"):        ChipSource("margin", "TPEx", "margin_tpex", "上櫃融資融券",
                                          fetch_tpex_margin, parse_tpex_margin, upsert_margin),
    ("sbl", "TWSE"):           ChipSource("sbl", "TWSE", "sbl_twse", "上市借券賣出",
                                          fetch_twse_sbl, parse_twse_sbl, upsert_sbl),
    ("foreign", "TWSE"):       ChipSource("foreign", "TWSE", "foreign_holding_twse", "上市外資持股",
                                          fetch_twse_foreign_holding, parse_twse_foreign_holding, upsert_foreign_holding),
}


def get_chip_source(kind: str, market: str) -> ChipSource:
    """取得指定籌碼來源。

    Raises:
        ValueError: 這個 kind × market 組合不存在（例如上櫃借券，M2 沒有來源）
    """
```

`get_chip_source` 的錯誤訊息要具體：
`f"沒有這個籌碼來源：kind={kind} market={market}；可用組合：" + "、".join(f"{k}/{m}" for k, m in CHIP_SOURCES)`。

### 3. `jobs.py`

```python
@dataclass(frozen=True)
class ChipJobResult:
    """單一交易日的籌碼載入結果。"""

    kind: str
    market: str
    trade_date: date
    rows: int
    skipped_unknown: int
    skip_reason: str | None = None


def load_chip_daily(
    engine: Engine,
    kind: str,
    market: str,
    trade_date: date,
    *,
    payload: dict | None = None,
    client: httpx.Client | None = None,
    check_calendar: bool = True,
    force: bool = False,
) -> ChipJobResult:
    """抓（或用傳入的）單一交易日的某類籌碼資料並寫入對應資料表，全程記 etl_job_log。

    Returns:
        ChipJobResult；被略過時 rows=0、skipped_unknown=0、skip_reason 為略過原因

    Raises:
        ValueError: kind × market 組合不存在
    """
```

主體**照抄 `load_daily_price` 的結構**，只把來源換成登錄表（一樣只能有一個 `return`）：

```python
    source = get_chip_source(kind, market)   # 組合不存在會在進 job_run 之前就拋 ValueError
    rows = 0
    skipped_unknown = 0

    with job_run(engine, source.job_name, target_date=trade_date) as run:
        with engine.begin() as conn:
            if not force and has_successful_run(conn, source.job_name, target_date=trade_date):
                run.skip("已完成，略過")
            if check_calendar:
                is_open = is_trading_day(conn, trade_date)
                if is_open is False:
                    run.skip("非開市日")
                elif is_open is None:
                    logger.warning("日曆缺少 %s", trade_date)

        if payload is None:
            payload = source.fetch(trade_date, client)

        records = source.parse(payload, trade_date)

        with engine.begin() as conn:
            upsert_result = source.upsert(conn, records)
        rows = upsert_result.written
        skipped_unknown = upsert_result.skipped_unknown
        run.rows = rows

    return ChipJobResult(
        kind=kind, market=market, trade_date=trade_date,
        rows=rows, skipped_unknown=skipped_unknown, skip_reason=run.note,
    )
```

### 4. `cli.py`：`load-chip` 子指令

```
load-chip --kind {institutional,margin,sbl,foreign} --market {TWSE,TPEx}
          [--date YYYY-MM-DD] [--file PATH] [--force] [--no-calendar-check]
```

- `--date` 預設台北時間今天（比照 `load-price`）。
- `--file` 讀 JSON（`json.loads(args.file.read_text(encoding="utf-8"))`）。
- 組合不存在時：`_cmd_load_chip` 自己先 `try: get_chip_source(...) except ValueError as exc: print(f"error: {exc}", file=sys.stderr); return 2`。**不要把 `ValueError` 加進 `main()` 的 `except` 串列**（會吃掉其他地方的程式錯誤）。
- 輸出：

| 情況 | 輸出（一行） |
| --- | --- |
| 正常載入 | `loaded kind=institutional market=TWSE date=2026-09-18 rows=3 skipped_unknown=1` |
| 被略過 | `skipped kind=institutional market=TWSE date=2026-09-18 reason=已完成，略過` |

成功回 `0`。

### 5. `cli.py`：`backfill chip` 子子指令

在 T2-1 建好的 `backfill` 底下再加一個 `chip`：

```
backfill chip --kind {institutional,margin,sbl,foreign} --market {TWSE,TPEx}
              --from YYYY-MM-DD --to YYYY-MM-DD [共用選項]
```

共用選項沿用 T2-1 的 `_add_backfill_common_options`。分派：
`elif args.backfill_command == "chip": summary = backfill_chip(engine, args.kind, args.market, args.start, args.end, options)`。
`BACKFILL_EPILOG` 的建議順序後面補三行：

```
  9.  python -m twstock_etl.cli backfill chip --kind institutional --market TWSE --from … --to …
  10. python -m twstock_etl.cli backfill chip --kind margin        --market TWSE --from … --to …
  （集保股權分散沒有回補：官方只留最新一週，用 load-shareholding 每週抓）
```

### 6. `backfill.py`：`backfill_chip`

```python
def backfill_chip(
    engine: Engine,
    kind: str,
    market: str,
    start: date,
    end: date,
    options: BackfillOptions,
) -> BackfillSummary:
    """逐交易日回補某一類籌碼資料。"""
```

**整支照抄 `backfill_prices`**，只改四個地方：

1. 開頭多一行 `source = get_chip_source(kind, market)`（組合錯誤在跑迴圈前就拋 `ValueError`）。
2. 斷點續傳查 `has_successful_run(conn, source.job_name, target_date=day)`。
3. 進度行的 `name` 改成 `f"{day.isoformat()} {market} {kind}"`。
4. 離線檔名改成 `f"{market}_{kind}_{day.strftime('%Y%m%d')}.json"`；執行改成
   `load_chip_daily(engine, kind, market, day, payload=payload)`。

其餘（`trading_days`、`RateLimiter`、`dry_run`、`max_failures`、`KeyboardInterrupt`、結尾統計行）一個字都不要改。

### 7. `scheduler.py`

```python
# 籌碼排程（台北時間）：(kind, market, 小時清單, 分鐘)
# 三大法人約 16:00–17:00 公布、外資持股盤後、融資融券與借券約 21:00 之後，各排三次靠 etl_job_log 去重
CHIP_SCHEDULE: tuple[tuple[str, str, str, int], ...] = (
    ("institutional", "TWSE", "16,18,20", 30),
    ("institutional", "TPEx", "16,18,20", 40),
    ("foreign",       "TWSE", "17,19,21", 0),
    ("margin",        "TWSE", "21,22,23", 30),
    ("margin",        "TPEx", "21,22,23", 40),
    ("sbl",           "TWSE", "21,22,23", 50),
)


def run_chip_job(engine: Engine, kind: str, market: str) -> None:
    """載入單日某類籌碼；失敗只記 log。"""
    try:
        today = datetime.now(TAIPEI).date()
        _log_job_outcome(
            f"{today} {get_chip_source(kind, market).label}",
            load_chip_daily(engine, kind, market, today),
        )
    except Exception:
        logger.exception("載入 %s %s 籌碼失敗", market, kind)
```

`build_scheduler()` 最後（集保那段之後）加：

```python
    for kind, market, hours, minute in CHIP_SCHEDULE:
        scheduler.add_job(
            run_chip_job,
            trigger=CronTrigger(hour=hours, minute=minute, timezone=TAIPEI),
            args=[engine, kind, market],
            id=get_chip_source(kind, market).job_name,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
```

### 8. 測試

`etl/tests/test_etl_chip_loaders.py`（需要 DB，`clean_db`；先塞 `2330`／`1101`／`2317`／`0050`／`3105`／`8069`，不塞 `9999`）：

1. `test_法人寫入三筆未知一筆`：`upsert_institutional` 用 `TWSE_institutional_20260918.json` 解析結果 → `written == 3`、`skipped_unknown == 1`。
2. `test_法人重跑不會變六筆`：跑兩次，`count(*) == 3`。
3. `test_融資融券寫入三筆`（`2330`／`1101`／`0050`，`9999` 被過濾）；`0050` 的 `margin_limit IS NULL`。
4. `test_借券只更新_sbl_欄位`：先 `upsert_margin`（09-18），再 `upsert_sbl`（09-18）→ `2330` 那列的 `margin_balance` 仍是 20,200,000、`sbl_balance` 是 4,500,000。
5. `test_借券可以先寫`：空表直接 `upsert_sbl` → `2330` 那列 `sbl_balance == 4_500_000`、`margin_balance == 0`、`source == "TWSE"`；之後再 `upsert_margin` → `margin_balance == 20_200_000` 且 `sbl_balance` 仍是 4,500,000。
6. `test_外資持股寫入兩筆`：`written == 2`（`2330`／`1101`）、`skipped_unknown == 1`；`holding_ratio == Decimal("70.0000")`。

`etl/tests/test_etl_chip_jobs.py`（需要 DB）：

7. `test_四種_kind_都能載入`：對 `("institutional","TWSE")`、`("margin","TWSE")`、`("sbl","TWSE")`、`("foreign","TWSE")` 各呼叫一次 `load_chip_daily(engine, kind, market, date(2026,9,18), payload=fixture, check_calendar=False)`，`skip_reason is None` 且 `rows > 0`。
8. `test_etl_job_log_的_job_name_正確`：查 `etl_job_log`，四次執行的 `job_name` 集合 == `{"institutional_twse", "margin_twse", "sbl_twse", "foreign_holding_twse"}`，全部 `status == "success"`、`target_date == date(2026,9,18)`。
9. `test_第二次會_skip`：再呼叫一次 `institutional/TWSE` → `rows == 0`、`skip_reason == "已完成，略過"`。
10. `test_force_可以重跑`。
11. `test_非開市日會_skip`：日曆把 2026-09-19 設成 `is_open=False`，`check_calendar=True` → `skip_reason == "非開市日"`。
12. `test_不存在的組合拋_ValueError`：`load_chip_daily(engine, "sbl", "TPEx", …)` → `pytest.raises(ValueError)`，**且 `etl_job_log` 沒有新增任何列**（因為在進 `job_run` 之前就拋）。
13. `test_上櫃法人載入`：`("institutional","TPEx")` 用 `TPEx_institutional_20260918.json` → `rows == 2`（`3105`／`8069`）、`skipped_unknown == 1`。

`etl/tests/test_etl_chip_backfill.py`（需要 DB）：

14. `test_離線回補三天`：日曆塞 2026-09-16/17/18 為開市日，`backfill_chip(engine, "institutional", "TWSE", date(2026,9,16), date(2026,9,18), BackfillOptions(sleep_seconds=0, source_dir=Path("etl/tests/fixtures"), out=io.StringIO()))` → `summary.done == 3`、`failed == 0`、`rows == 9`。
15. `test_再跑一次全部_skip`：`summary.skipped == 3`、`done == 0`，輸出三行都含 `skip`。
16. `test_檔案不存在算一次失敗`：回補 `sbl`（只有 09-18 有 fixture）三天 → `failed == 2`、`done == 1`，輸出含兩行 `FAIL`。
17. `test_進度行格式`：輸出第一行符合 `^\[   1/   3\] 2026-09-16 TWSE institutional rows=3 `。

`etl/tests/test_etl_cli.py` 加：

18. `test_load_chip_輸出格式`（monkeypatch `load_chip_daily`）。
19. `test_load_chip_skip_輸出格式`。
20. `test_load_chip_不存在的組合回_2`：`main(["load-chip", "--kind", "sbl", "--market", "TPEx"])` → 回 `2`，stderr 含「沒有這個籌碼來源」。
21. `test_backfill_chip_帶對參數`（monkeypatch `backfill_chip`）。

`etl/tests/test_etl_scheduler.py` 加：

22. `test_六個籌碼_job_都註冊`：`build_scheduler(engine)` 取得六個 job id（`institutional_twse`、`institutional_tpex`、`margin_twse`、`margin_tpex`、`sbl_twse`、`foreign_holding_twse`）都不是 `None`。
23. `test_run_chip_job_略過時不記_ERROR`（同 T2-3 的第 12 點寫法）。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed；skipped 只有 TimescaleDB 那一筆

cd /home/claude/TwStock && export DATABASE_URL=$(TWSTOCK_PGDATA=/tmp/twstock-pg-t26 TWSTOCK_PGPORT=54346 scripts/pg_temp.sh reset) && \
  .venv/bin/alembic -c db/alembic.ini upgrade head >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-stocks --market TPEx --file etl/tests/fixtures/isin_tpex_strmode4.html >/dev/null && \
  .venv/bin/python -m twstock_etl.cli load-calendar --year 2026 --file etl/tests/fixtures/twse_holiday_schedule_2026.json >/dev/null && \
  .venv/bin/python -m twstock_etl.cli backfill chip --kind institutional --market TWSE --from 2026-09-16 --to 2026-09-18 --source-dir etl/tests/fixtures --sleep 0 | tail -1 && \
  .venv/bin/python -m twstock_etl.cli load-chip --kind margin --market TWSE --date 2026-09-18 --file etl/tests/fixtures/TWSE_margin_20260918.json && \
  .venv/bin/python -m twstock_etl.cli load-chip --kind sbl --market TWSE --date 2026-09-18 --file etl/tests/fixtures/TWSE_sbl_20260918.json && \
  .venv/bin/python -m twstock_etl.cli load-chip --kind foreign --market TWSE --date 2026-09-18 --file etl/tests/fixtures/TWSE_foreign_20260918.json
# 預期（四行）：
# 完成 3／跳過 0／失敗 0，共寫入 9 筆，耗時 00:00:0X
# loaded kind=margin market=TWSE date=2026-09-18 rows=3 skipped_unknown=1
# loaded kind=sbl market=TWSE date=2026-09-18 rows=2 skipped_unknown=1
# loaded kind=foreign market=TWSE date=2026-09-18 rows=2 skipped_unknown=1

cd /home/claude/TwStock && /usr/lib/postgresql/16/bin/psql "$(echo $DATABASE_URL | sed 's|postgresql+psycopg|postgresql|')" \
  -c "SELECT trade_date, foreign_net, trust_net, dealer_net, total_net FROM institutional_daily WHERE stock_id='2330' ORDER BY trade_date" \
  -c "SELECT margin_balance, short_balance, sbl_sell, sbl_balance FROM margin_daily WHERE stock_id='2330' AND trade_date='2026-09-18'"
# 預期：法人三列 5000000/8000000/12000000（foreign_net），最後一列 total_net=13500000
#       融資券一列 20200000 | 1090000 | 300000 | 4500000

cd /home/claude/TwStock && scripts/m1_verify.sh | tail -1
# 預期：M1 VERIFY PASSED（回歸）
```

### 不要做的事

- **不要**為每一類籌碼各寫一個 job 函式、一個 CLI 子指令、一個排程 wrapper（D-034：全部走 `CHIP_SOURCES`）。
- 不要讓 `upsert_sbl` 更新融資融券欄位，也不要讓 `upsert_margin` 更新 `sbl_*`。
- 不要為集保加回補子指令。
- 不要動 `backfill_prices` / `backfill_index` / `backfill_exright` / `backfill_calendar` 的既有程式。
- 不要把 `ValueError` 加進 `cli.main()` 的 `except` 串列。
- 不要寫 API 或前端。

---

## T2-7　API：四個籌碼端點，與後端整合驗收腳本

### 目標

把四張籌碼表開成 §5 的四個 API 端點，並寫出本里程碑的後端完成標準腳本 `scripts/m2_verify.sh`。

### 新增 / 修改檔案

```
api/twstock_api/chip_repository.py    # 新增
api/twstock_api/routers/chips.py      # 新增
api/twstock_api/schemas.py            # 改：加 7 個 schema
api/twstock_api/main.py               # 改：掛 chips router
api/tests/test_api_chips.py           # 新增
api/tests/test_api_shareholding.py    # 新增
scripts/verify_chips.py               # 新增
scripts/m2_verify.sh                  # 新增
```

**只准動上面 8 個檔案。**

### 1. `chip_repository.py`

```python
"""籌碼資料庫查詢模組。"""

MAX_LIMIT = 6000
DEFAULT_LIMIT = 2000
SHAREHOLDING_MAX_LIMIT = 520
SHAREHOLDING_DEFAULT_LIMIT = 104
DEFAULT_WINDOW_DAYS = 365
BIG_HOLDER_LEVELS = range(12, 16)   # 400 張以上（D-038）
RETAIL_LEVELS = range(1, 5)         # 15 張以下（D-038）


def latest_chip_date(conn: Connection, kind: str, stock_id: str) -> date | None:
    """該股在某張籌碼表的最新日期；kind ∈ institutional / margin / foreign / shareholding。"""


def fetch_institutional(conn, stock_id: str, start: date, end: date, limit: int) -> list[dict[str, Any]]: ...
def fetch_margin(conn, stock_id: str, start: date, end: date, limit: int) -> list[dict[str, Any]]: ...
def fetch_foreign_holding(conn, stock_id: str, start: date, end: date, limit: int) -> list[dict[str, Any]]: ...
def fetch_shareholding(conn, stock_id: str, start: date, end: date, limit: int) -> list[dict[str, Any]]: ...
```

- **SQL 一律是寫死的 `text(...)` 常數 + 具名參數**，`kind` 只能當作 dict 的 key 去查預先寫好的 SQL，**絕對不要把表名字串拼進 SQL**：

```python
_LATEST_DATE_SQL: dict[str, TextClause] = {
    "institutional": text("SELECT MAX(trade_date) FROM institutional_daily WHERE stock_id = :stock_id"),
    "margin":        text("SELECT MAX(trade_date) FROM margin_daily WHERE stock_id = :stock_id"),
    "foreign":       text("SELECT MAX(trade_date) FROM foreign_holding WHERE stock_id = :stock_id"),
    "shareholding":  text("SELECT MAX(week_date) FROM shareholding_dist WHERE stock_id = :stock_id"),
}
```
  `kind` 不在字典裡 → `raise ValueError(f"不支援的籌碼種類：{kind}")`。

- `fetch_institutional` / `fetch_margin` / `fetch_foreign_holding` 的作法**完全比照 M1 `price_repository.fetch_prices`**：
  `ORDER BY trade_date DESC LIMIT :limit` 取回後在 Python `reverse()`，確保超過上限時保留最新的。
  取的欄位：
  - 法人：`trade_date, foreign_buy, foreign_sell, foreign_net, trust_buy, trust_sell, trust_net, dealer_buy, dealer_sell, dealer_net, total_net`
  - 融資券：`trade_date, margin_buy, margin_sell, margin_redeem, margin_prev_balance, margin_balance, margin_limit, short_buy, short_sell, short_redeem, short_prev_balance, short_balance, short_limit, offset_amount, sbl_sell, sbl_balance`
  - 外資持股：`trade_date, issued_shares, holding_shares, available_shares, holding_ratio, available_ratio, limit_ratio`

- `fetch_shareholding` 分兩次查（避免 `GROUP BY` 之後還要 `LIMIT` 週數）：

```python
    weeks_sql = text("""
        SELECT DISTINCT week_date FROM shareholding_dist
        WHERE stock_id = :stock_id AND week_date >= :start AND week_date <= :end
        ORDER BY week_date DESC LIMIT :limit
    """)
    rows_sql = text("""
        SELECT week_date, level, holders, shares, ratio FROM shareholding_dist
        WHERE stock_id = :stock_id AND week_date = ANY(:weeks)
        ORDER BY week_date, level
    """)
```
  再在 Python 依 `week_date` 分組，每組產出：

```python
    {
      "week_date": <date>,
      "total_holders": <level 16 的 holders；沒有 16 時為 level 1–15 的 holders 總和>,
      "total_shares": <level 16 的 shares；沒有 16 時為 level 1–15 的 shares 總和>,
      "big_holder_ratio": <level 12–15 的 ratio 相加，Decimal，quantize 到 0.0001>,
      "retail_ratio":     <level 1–4 的 ratio 相加，Decimal，quantize 到 0.0001>,
      "levels": [ {"level": int, "holders": int, "shares": int, "ratio": Decimal}, … ],  # 只含 1–15，依 level 升冪
    }
```
  回傳清單依 `week_date` **升冪**。

### 2. `schemas.py` 新增

```python
class InstitutionalBar(BaseModel):
    """一天的三大法人買賣超（股）。"""
    time: date
    foreign_buy: int
    foreign_sell: int
    foreign_net: int
    trust_buy: int
    trust_sell: int
    trust_net: int
    dealer_buy: int
    dealer_sell: int
    dealer_net: int
    total_net: int


class MarginBar(BaseModel):
    """一天的融資融券與借券（股）。"""
    time: date
    margin_buy: int
    margin_sell: int
    margin_redeem: int
    margin_prev_balance: int
    margin_balance: int
    margin_limit: int | None
    short_buy: int
    short_sell: int
    short_redeem: int
    short_prev_balance: int
    short_balance: int
    short_limit: int | None
    offset_amount: int
    sbl_sell: int | None
    sbl_balance: int | None
    margin_ratio: float | None


class ForeignHoldingBar(BaseModel):
    """一天的外資持股。"""
    time: date
    issued_shares: int | None
    holding_shares: int
    available_shares: int | None
    holding_ratio: float | None
    available_ratio: float | None
    limit_ratio: float | None


class ShareholdingLevel(BaseModel):
    """集保股權分散的一個級距。"""
    level: int
    holders: int
    shares: int
    ratio: float


class ShareholdingWeek(BaseModel):
    """集保股權分散的一週。"""
    week: date
    total_holders: int
    total_shares: int
    big_holder_ratio: float
    retail_ratio: float
    levels: list[ShareholdingLevel]
```

再加四個回應模型 `InstitutionalResponse`、`MarginResponse`、`ForeignHoldingResponse`、`ShareholdingResponse`，
欄位一律 `stock_id / name / market / from_（alias "from"）/ to / count / items`，
`model_config = ConfigDict(populate_by_name=True)`（完全比照 M1 的 `PriceResponse`）。

`margin_ratio` 在 router 算：`short_balance / margin_balance * 100`，用 `Decimal` 算完再
`.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)` 轉 `float`；`margin_balance == 0` → `None`。

### 3. `routers/chips.py`

```python
router = APIRouter(prefix="/api/stocks", tags=["chips"])


def _resolve(
    conn: Connection, stock_id: str, from_: date | None, to: date | None, kind: str
) -> tuple[dict[str, Any], date, date]:
    """共用的「查個股 + 決定日期區間」流程；四個端點都呼叫它。

    Raises:
        HTTPException: 404 個股不存在、422 from > to
    """
    stock = get_stock(conn, stock_id)
    if not stock:
        raise HTTPException(status_code=404, detail=f"查無此個股：{stock_id}")
    if to is None:
        latest = latest_chip_date(conn, kind, stock_id)
        to = latest if latest is not None else datetime.now(ZoneInfo("Asia/Taipei")).date()
    if from_ is None:
        from_ = to - timedelta(days=DEFAULT_WINDOW_DAYS)
    if from_ > to:
        raise HTTPException(status_code=422, detail="from 不可晚於 to")
    return stock, from_, to
```

四個端點（`get_stock` 從 `twstock_api.price_repository` import，**不要複製一份**）：

| 路徑 | `kind` | `limit` | fetch |
| --- | --- | --- | --- |
| `GET /{stock_id}/institutional` | `institutional` | `Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)` | `fetch_institutional` |
| `GET /{stock_id}/margin` | `margin` | 同上 | `fetch_margin` |
| `GET /{stock_id}/foreign-holding` | `foreign` | 同上 | `fetch_foreign_holding` |
| `GET /{stock_id}/shareholding` | `shareholding` | `Query(default=SHAREHOLDING_DEFAULT_LIMIT, ge=1, le=SHAREHOLDING_MAX_LIMIT)` | `fetch_shareholding` |

全部用 `from_: date | None = Query(default=None, alias="from")`、`to: date | None = Query(default=None)`、`engine: Engine = Depends(get_db_engine)`，並用 `with engine.connect() as conn:`。
`Decimal → float` 一律 `float(x) if x is not None else None`。

`main.py` 加 `from twstock_api.routers import chips` 與 `app.include_router(chips.router)`（放在 `prices` 之後）。

### 4. `scripts/verify_chips.py`

比照 M1 `scripts/verify_prices.py` 的寫法（`urllib.request` + `argparse --api-base`，預設 `http://127.0.0.1:18002`），依序做 10 項核對，每項印 `OK <名稱> <說明>` 或 `FAIL <名稱> <實際值>`：

| # | 名稱 | 請求 | 通過條件 |
| --- | --- | --- | --- |
| 1 | `inst-series` | `/api/stocks/2330/institutional?from=2026-09-16&to=2026-09-18` | `count == 3` 且 `[i["foreign_net"] for i in items] == [5000000, 8000000, 12000000]` |
| 2 | `inst-detail` | 同上 | 最後一筆 `foreign_buy == 30000000`、`foreign_sell == 18000000`、`trust_net == 2000000`、`dealer_net == -500000`、`total_net == 13500000` |
| 3 | `margin-series` | `/api/stocks/2330/margin?from=2026-09-16&to=2026-09-18` | `[i["margin_balance"] …] == [19500000, 20000000, 20200000]` 且 `[i["short_balance"] …] == [900000, 1000000, 1090000]` |
| 4 | `margin-sbl` | 同上 | 最後一筆 `sbl_sell == 300000`、`sbl_balance == 4500000`；**第一筆 `sbl_sell is None`**（借券只有 09-18 有資料，證明部分欄位 upsert 沒有覆蓋融資券） |
| 5 | `margin-ratio` | 同上 | 最後一筆 `margin_ratio == 5.396` |
| 6 | `foreign-holding` | `/api/stocks/2330/foreign-holding` | `count == 1`、`holding_shares == 18151266320`、`holding_ratio == 70.0`、`available_ratio == 30.0` |
| 7 | `shareholding` | `/api/stocks/2330/shareholding` | `count == 1`、`big_holder_ratio == 80.0`、`retail_ratio == 20.0`、`total_holders == 1000000`、`total_shares == 1000000000`、`len(levels) == 7`（只有 1–15，不含 16） |
| 8 | `tpex-inst` | `/api/stocks/3105/institutional` | 最後一筆 `foreign_net == 550000`、`total_net == 630000` |
| 9 | `empty-range` | `/api/stocks/2330/institutional?from=2020-01-01&to=2020-01-31` | HTTP 200、`count == 0`、`items == []` |
| 10 | `unknown-stock` | `/api/stocks/9999/institutional` | HTTP 404 |

全部通過 → 印 `OK all 10 chip checks passed` 回 0；否則印失敗項目與 `FAILED n/10` 回 1。

### 5. `scripts/m2_verify.sh`

`set -euo pipefail`、`ROOT="$(cd "$(dirname "$0")/.." && pwd)"`、獨立叢集
`TWSTOCK_PGDATA=/tmp/twstock-pg-m2`、`TWSTOCK_PGPORT=54332`、API port `18002`、
`trap` 在 EXIT 時 kill uvicorn 並 `pg_temp.sh stop`（結構整段照抄 `scripts/m1_verify.sh`，只改叢集路徑、port 與步驟）。步驟：

```
== reset database     pg_temp.sh reset
== migrate            alembic upgrade head
== load fixtures      load-stocks TWSE / TPEx、load-calendar 2026
== backfill price     cli backfill index   --from 2026-09 --to 2026-09 --source-dir <fixtures> --sleep 0
                      cli backfill price   --market TWSE --from 2026-09-16 --to 2026-09-18 --source-dir <fixtures> --sleep 0
                      cli backfill price   --market TPEx --from 2026-09-16 --to 2026-09-18 --source-dir <fixtures> --sleep 0
                      cli backfill exright --from 2026-09-01 --to 2026-09-30 --source-dir <fixtures> --sleep 0
== load shareholding  cli load-shareholding --file <fixtures>/tdcc_shareholding_20260918.csv
== backfill chip      cli backfill chip --kind institutional --market TWSE --from 2026-09-16 --to 2026-09-18 --source-dir <fixtures> --sleep 0
                      cli backfill chip --kind margin        --market TWSE --from 2026-09-16 --to 2026-09-18 --source-dir <fixtures> --sleep 0
== load chip single   cli load-chip --kind institutional --market TPEx --date 2026-09-18 --file <fixtures>/TPEx_institutional_20260918.json
                      cli load-chip --kind margin        --market TPEx --date 2026-09-18 --file <fixtures>/TPEx_margin_20260918.json
                      cli load-chip --kind sbl           --market TWSE --date 2026-09-18 --file <fixtures>/TWSE_sbl_20260918.json
                      cli load-chip --kind foreign       --market TWSE --date 2026-09-18 --file <fixtures>/TWSE_foreign_20260918.json
== resume check       再跑一次 backfill chip institutional TWSE，輸出必須剛好 3 行含 skip（grep -c skip = 3）
                      再跑一次 load-shareholding，輸出必須含 "skipped shareholding"
== start api          uvicorn twstock_api.main:app --host 127.0.0.1 --port 18002
== verify chips       scripts/verify_chips.py --api-base http://127.0.0.1:18002
== verify prices      scripts/verify_prices.py --api-base http://127.0.0.1:18002   ← 順便回歸 M1 的 9 項
M2 VERIFY PASSED
```

腳本要能**重複執行**（每次 `pg_temp.sh reset`）。`chmod +x scripts/m2_verify.sh`。

### 6. 測試

`api/tests/test_api_chips.py`（需要 DB，比照既有 `api/tests/test_api_prices.py` 的作法建 `TestClient` 與塞資料）：

1. `test_法人端點三天升冪`。
2. `test_法人端點欄位齊全`：回應 item 的 key 集合 == §5.1 的 11 個 key。
3. `test_融資券端點_margin_ratio`：`margin_balance=20200000`、`short_balance=1090000` → `margin_ratio == 5.396`。
4. `test_margin_balance_為零時_margin_ratio_是_None`。
5. `test_sbl_沒資料時是_None`。
6. `test_外資持股端點`。
7. `test_from_大於_to_回_422`。
8. `test_個股不存在回_404`。
9. `test_區間內無資料回_200_count_0`。
10. `test_limit_取最新的幾筆`：塞 5 天、`limit=2` → 回最後兩天且升冪。

`api/tests/test_api_shareholding.py`（需要 DB）：

11. `test_單週分組與大戶比例`：塞 fixture 的 `2330` 八列 → `count == 1`、`big_holder_ratio == 80.0`、`retail_ratio == 20.0`、`total_holders == 1000000`、`len(levels) == 7`。
12. `test_沒有_level_16_時_total_用_1_到_15_加總`。
13. `test_limit_取最新幾週`：塞三週、`limit=2` → 回最新兩週且依 `week` 升冪。
14. `test_level_16_17_不出現在_levels`。

### 驗收指令

```bash
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：全部 passed；skipped 只有 TimescaleDB 那一筆

cd /home/claude/TwStock && scripts/m2_verify.sh
# 預期最後幾行：
# OK all 10 chip checks passed
# OK all 9 price checks passed
# M2 VERIFY PASSED

cd /home/claude/TwStock && scripts/m2_verify.sh >/dev/null && scripts/m2_verify.sh | tail -1
# 預期：可重複執行，仍為 M2 VERIFY PASSED

cd /home/claude/TwStock && scripts/m1_verify.sh | tail -1
# 預期：M1 VERIFY PASSED（兩支腳本用不同的叢集與 port，可以並存）
```

### 不要做的事

- 不要把表名或欄位名用字串拼進 SQL（`kind` 只能查預先寫好的 SQL 字典）。
- 不要在 API 層改寫或補算籌碼數字（只有 `margin_ratio`、`big_holder_ratio`、`retail_ratio` 三個是算出來的）。
- 不要做寫入型 API（ETL 手動重跑留到 M3）。
- 不要動 M1 的五個端點與 `price_repository.py`。
- 不要碰前端。

---

## T2-8　前端：副圖與主圖十字線同步、籌碼分頁

### 目標

個股頁改成「K 線」與「籌碼」兩個分頁；K 線分頁是多個 pane 疊在一起（主圖 K 線＋成交量＋三大法人買賣超＋融資融券餘額），
**四個 pane 共用同一條十字線與同一個時間軸，滑鼠移到哪天，上方讀數面板就顯示那天的所有數字**——這就是 M2 的完成標準。

### 新增 / 修改檔案

```
web/src/api.ts                             # 改：加 4 組型別與 fetch 函式
web/src/chartSync.ts                       # 新增（十字線同步純函式）
web/src/chartSync.test.ts                  # 新增
web/src/chipMath.ts                        # 新增（連買天數等純計算）
web/src/chipMath.test.ts                   # 新增
web/src/components/ChartStack.tsx          # 新增
web/src/components/ChartStack.test.tsx     # 新增
web/src/components/ChipTab.tsx             # 新增
web/src/components/ChipTab.test.tsx        # 新增
web/src/components/CandleChart.tsx         # 刪除
web/src/pages/StockPage.tsx                # 改寫
web/src/pages/StockPage.test.tsx           # 改寫
web/src/styles.css                         # 改：加樣式
```

**只准動上面 13 個檔案**（`CandleChart.tsx` 是刪除，不是保留不用）。
`web/package.json` **不准改**（不新增、不升級任何套件）。

### 1. `web/src/api.ts` 新增

型別（欄位與 §5 的 JSON 逐欄一致）：

```ts
export interface InstitutionalBar {
  time: string
  foreign_buy: number; foreign_sell: number; foreign_net: number
  trust_buy: number; trust_sell: number; trust_net: number
  dealer_buy: number; dealer_sell: number; dealer_net: number
  total_net: number
}

export interface MarginBar {
  time: string
  margin_buy: number; margin_sell: number; margin_redeem: number
  margin_prev_balance: number; margin_balance: number; margin_limit: number | null
  short_buy: number; short_sell: number; short_redeem: number
  short_prev_balance: number; short_balance: number; short_limit: number | null
  offset_amount: number
  sbl_sell: number | null; sbl_balance: number | null
  margin_ratio: number | null
}

export interface ForeignHoldingBar {
  time: string
  issued_shares: number | null; holding_shares: number
  available_shares: number | null
  holding_ratio: number | null; available_ratio: number | null; limit_ratio: number | null
}

export interface ShareholdingLevel { level: number; holders: number; shares: number; ratio: number }

export interface ShareholdingWeek {
  week: string
  total_holders: number; total_shares: number
  big_holder_ratio: number; retail_ratio: number
  levels: ShareholdingLevel[]
}
```

四個 fetch 函式，簽名與錯誤處理**完全比照既有的 `fetchPrices`**（用 `new URL(path, window.location.origin)` 組參數、非 2xx 丟 `Error('HTTP ' + status)`）：

```ts
export async function fetchInstitutional(stockId: string, params: { from?: string; to?: string; limit?: number }, signal?: AbortSignal): Promise<{ stock_id: string; count: number; items: InstitutionalBar[] }>
export async function fetchMargin(...): Promise<{ …; items: MarginBar[] }>
export async function fetchForeignHolding(...): Promise<{ …; items: ForeignHoldingBar[] }>
export async function fetchShareholding(stockId: string, params: { from?: string; to?: string; limit?: number }, signal?: AbortSignal): Promise<{ …; items: ShareholdingWeek[] }>
```

路徑分別是 `/api/stocks/{id}/institutional`、`/margin`、`/foreign-holding`、`/shareholding`。

### 2. `web/src/chartSync.ts`（本任務的核心，要能被單元測試）

```ts
import type { IChartApi, ISeriesApi, SeriesType, Time } from 'lightweight-charts'

/** 一個可被同步的 pane。chart 只用到兩個方法，方便測試時傳假物件。 */
export interface SyncPane {
  id: string
  chart: Pick<IChartApi, 'setCrosshairPosition' | 'clearCrosshairPosition'>
  series: ISeriesApi<SeriesType>
  /** 這個 pane 在每個日期的代表值，決定十字線的垂直位置（主圖用收盤、成交量用量…） */
  valueByTime: Map<string, number>
}

/**
 * 把來源 pane 的十字線時間套到其他所有 pane。
 * time 為 null（滑鼠移出圖表或不在資料範圍內）時，其他 pane 一律清掉十字線。
 */
export function applyCrosshairToOthers(
  panes: SyncPane[],
  sourceId: string,
  time: string | null
): void {
  for (const pane of panes) {
    if (pane.id === sourceId) continue
    if (time === null) {
      pane.chart.clearCrosshairPosition()
      continue
    }
    const value = pane.valueByTime.get(time)
    if (value === undefined) {
      pane.chart.clearCrosshairPosition()
      continue
    }
    pane.chart.setCrosshairPosition(value, time as Time, pane.series)
  }
}

/** 把 lightweight-charts 的 crosshair 事件參數轉成 'YYYY-MM-DD' 或 null。 */
export function crosshairTime(param: { time?: unknown }): string | null {
  const t = param.time
  return typeof t === 'string' && t.length === 10 ? t : null
}

/** 用日期字串在一組時間序列裡找索引；找不到回 -1。 */
export function indexOfTime(times: string[], time: string): number
```

**不要**在這支檔案 import React 或任何元件。

### 3. `web/src/chipMath.ts`

```ts
/** 連續買超（正）／賣超（負）天數：從最後一天往回數，方向改變或遇到 0 就停。 */
export function consecutiveDays(nets: number[]): { days: number; direction: 'buy' | 'sell' | 'none' }

/** 股 → 張的顯示字串（整數、千分位）；例 20_200_000 → "20,200"。 */
export function toLots(shares: number | null | undefined): string

/** 百分比顯示；null → "—"；例 70 → "70.00%"。 */
export function toPercent(value: number | null | undefined): string
```

`consecutiveDays` 規則：`nets` 為空或最後一個是 0 → `{ days: 0, direction: 'none' }`；
否則方向由最後一個的正負決定，從尾端往前數同號的連續個數。
`toLots`：`Math.round(shares / 1000).toLocaleString('en-US')`；`null`／`undefined` → `"—"`。

### 4. `web/src/components/ChartStack.tsx`

```tsx
export interface ChartStackProps {
  bars: PriceBar[]
  institutional: InstitutionalBar[]
  margin: MarginBar[]
  showInstitutional: boolean
  showMargin: boolean
  maPeriods?: number[]   // 預設 [5, 20, 60]
}
```

#### 4.1 版面

```tsx
<div className="chart-stack">
  <div className="chart-readout" data-testid="chart-readout"> …見 §4.4… </div>
  <div ref={mainRef} className="chart-pane chart-pane-main" />
  <div ref={volumeRef} className="chart-pane" />
  {showInstitutional && <div ref={instRef} className="chart-pane" />}
  {showMargin && <div ref={marginRef} className="chart-pane" />}
</div>
```

每個 pane 上方要有一行 `<div className="chart-pane-title">` 標題：`K 線`、`成交量（張）`、`三大法人買賣超（張）`、`融資融券餘額（張）`。

#### 4.2 建圖（**一個 `useEffect` 做完全部**）

```tsx
useEffect(() => { … }, [bars, institutional, margin, showInstitutional, showMargin, maPeriods])
```

這個 effect 會在每次資料或開關變動時**整組重建圖表**，cleanup 裡把所有 chart `remove()`。
（重建成本對本專案可接受，換來的是不必維護「series 已存在但資料換了」的狀態機——M1 的 T1-4 就是被這種狀態機拖垮的。）

建圖共用選項（每個 pane 都一樣，`minimumWidth` 是讓所有 pane 的 x 軸對齊的關鍵）：

```ts
const common = {
  width: el.clientWidth,
  rightPriceScale: { minimumWidth: 72 },
  leftPriceScale: { visible: false },
  crosshair: { mode: CrosshairMode.Normal },   // 不要用 Magnet，副圖會對不準
  timeScale: { timeVisible: false, secondsVisible: false },
}
```

- 高度：主圖 `360`、其他 pane `110`。
- **只有最後一個 pane 顯示時間軸**：其餘 `chart.applyOptions({ timeScale: { visible: false } })`。
- 有效 K 棒：`bars.filter(b => b.open !== null && b.high !== null && b.low !== null && b.close !== null)`；為空就直接 `return`（不要建圖）。

各 pane 的 series：

| pane id | series | 資料 | `valueByTime` |
| --- | --- | --- | --- |
| `main` | `addCandlestickSeries({ upColor:'#d32f2f', downColor:'#2e7d32', borderUpColor:'#d32f2f', borderDownColor:'#2e7d32', wickUpColor:'#d32f2f', wickDownColor:'#2e7d32' })` ＋ `maPeriods` 條 `addLineSeries`（顏色沿用 M1 的 `['#f9a825','#1e88e5','#8e24aa','#00897b']`，均線用既有的 `simpleMovingAverage`） | `{time, open, high, low, close}` | 收盤價 |
| `volume` | `addHistogramSeries({ priceFormat: { type: 'volume' } })` | `{time, value: volume, color: close >= open ? '#d32f2f' : '#2e7d32'}` | `volume` |
| `institutional` | `addHistogramSeries({ priceFormat: { type: 'volume' } })` | `{time, value: total_net, color: total_net >= 0 ? '#d32f2f' : '#2e7d32'}` | `total_net` |
| `margin` | `addLineSeries({ color:'#f57c00', lineWidth:1 })`（融資餘額）＋ `addLineSeries({ color:'#1e88e5', lineWidth:1 })`（融券餘額） | `{time, value: margin_balance}` / `{time, value: short_balance}` | `margin_balance` |

> **不做三大法人堆疊柱**（D-039）：Lightweight Charts 的 histogram 一律從 `base` 畫起，做不出正負混合的堆疊；
> M2 副圖畫「三大法人合計買賣超」單一柱，外資／投信／自營三個數字改由讀數面板與籌碼分頁提供。

法人與融資券資料的時間可能少於 K 線（例如借券只有一天），**series 只放該資料自己有的日期**，不要補 0。

#### 4.3 同步

建完所有 pane 後組出 `panes: SyncPane[]`（順序同版面），然後：

```ts
// 時間軸同步（沿用 M1 CandleChart 的 syncingRef 防迴圈寫法）
for (const p of panes) {
  p.rawChart.timeScale().subscribeVisibleLogicalRangeChange(() => {
    if (syncingRef.current) return
    syncingRef.current = true
    const range = p.rawChart.timeScale().getVisibleLogicalRange()
    if (range) for (const q of panes) if (q !== p) q.rawChart.timeScale().setVisibleLogicalRange(range)
    syncingRef.current = false
  })
  // 十字線同步 + 讀數面板
  p.rawChart.subscribeCrosshairMove((param) => {
    const t = crosshairTime(param)
    applyCrosshairToOthers(panes, p.id, t)
    setHoverTime(t)
  })
}
```

（`SyncPane` 只宣告 `chart` 的兩個方法，實作上把完整的 `IChartApi` 傳進去即可；`rawChart` 是同一個物件，只是為了在 effect 裡叫 `timeScale()` / `subscribeCrosshairMove()`。）

最後 `panes[0].rawChart.timeScale().fitContent()`，並用一個 `ResizeObserver` 監看主 pane 寬度，變動時對每個 chart `applyOptions({ width })`。
cleanup：`resizeObserver.disconnect()` 後對每個 chart `remove()`。

#### 4.4 讀數面板

```tsx
const [hoverTime, setHoverTime] = useState<string | null>(null)
```

顯示的那一天 = `hoverTime` 有值且在 `bars` 裡找得到就用它，否則用**最後一根 K 棒的日期**。
面板是一列（手機寬度自動換行）的標籤＋數值，每個數值都要有 `data-testid`：

| `data-testid` | 內容 | 找不到資料時 |
| --- | --- | --- |
| `readout-date` | 日期字串（`YYYY-MM-DD`） | `—` |
| `readout-ohlc` | `開 996.00 高 1010.00 低 995.00 收 1008.00`（各 2 位小數） | `—` |
| `readout-change` | `+13.00`／`-5.00`（2 位小數，`className` 為 `up`／`down`） | `—` |
| `readout-volume` | `toLots(volume)` | `—` |
| `readout-foreign` | `toLots(foreign_net)`（`className` 依正負 `up`／`down`） | `—` |
| `readout-trust` | `toLots(trust_net)` | `—` |
| `readout-dealer` | `toLots(dealer_net)` | `—` |
| `readout-margin` | `toLots(margin_balance)` | `—` |
| `readout-short` | `toLots(short_balance)` | `—` |

標籤文字固定為「日期」「開高低收」「漲跌」「成交量」「外資」「投信」「自營」「融資餘額」「融券餘額」。

### 5. `web/src/components/ChipTab.tsx`

```tsx
export interface ChipTabProps {
  bars: PriceBar[]
  institutional: InstitutionalBar[]
  shareholding: ShareholdingWeek[]
  foreignHolding: ForeignHoldingBar[]
}
```

三個區塊，各有 `<h2>` 標題。**不要**在這支檔案用 lightweight-charts；趨勢圖用同檔案內自己寫的一個小 `Sparkline` 元件（純 inline SVG，約 25 行）：

```tsx
function Sparkline(props: { values: number[]; width?: number; height?: number; color?: string }) {
  // 把 values 正規化到 0..1 後畫一條 <polyline>；values 少於 2 個時回 null
  // <svg role="img" aria-label="趨勢圖" …><polyline points="…" fill="none" stroke={color} strokeWidth="1.5" /></svg>
}
```

#### 5.1 集保股權分散

- 沒有資料 → `<p>尚無集保股權分散資料，請先執行 load-shareholding。</p>`
- 有資料：
  - 一行摘要：`資料週 2026-09-18 · 總股東人數 1,000,000 人`（`data-testid="chip-week"`）
  - 兩個大數字：`400 張以上大戶比例 80.00%`（`data-testid="chip-big-ratio"`）、`15 張以下散戶比例 20.00%`（`data-testid="chip-retail-ratio"`）
  - `<Sparkline>`：近 N 週的 `big_holder_ratio`
  - 最新一週的級距表：欄位「級距」「人數」「股數（張）」「比例」，級距文字用 §3 的對照表（寫成一個 `LEVEL_LABELS: Record<number, string>` 常數，只需 1–15）

#### 5.2 外資持股比例趨勢

- 沒有資料 → `<p>尚無外資持股資料（M2 只收上市）。</p>`
- 有資料：最新一筆 `外資持股比例 70.00%`（`data-testid="chip-foreign-ratio"`）＋ `尚可投資比例 30.00%` ＋ `<Sparkline>`（`holding_ratio` 序列）

#### 5.3 法人連續買賣天數

- 三行：`外資 連買 3 天`、`投信 連買 1 天`、`自營 連賣 1 天`，各有 `data-testid="chip-streak-foreign"`／`-trust`／`-dealer`；
  `direction === 'none'` 時顯示 `外資 —`。用 `consecutiveDays()` 算（輸入是依時間升冪的 `foreign_net` / `trust_net` / `dealer_net` 陣列）。
- 下方「最近 20 日法人買賣超（張）」表格：日期、外資、投信、自營、合計（取 `institutional` 最後 20 筆，**由新到舊**顯示）。

### 6. `web/src/pages/StockPage.tsx`

在 M1 版本上改：

1. **分頁**：`const [tab, setTab] = useState<'chart' | 'chip'>('chart')`。
   兩個 `<button role="tab" aria-selected={…}>`，文字「K 線」「籌碼」，包在 `<div role="tablist">` 裡。分頁選擇存 `localStorage` key `twstock.stockPage.tab`。
2. **副圖開關**：兩個 checkbox，label 文字「法人買賣超」「融資融券」，預設都勾選，分別存 `localStorage` key `twstock.stockPage.showInstitutional` / `…showMargin`。只在 `tab === 'chart'` 時顯示。
3. **資料載入**：同一個 `useEffect`（deps `[stockId, range, adjusted]`）用 `Promise.allSettled` 同時取六份資料：
   `fetchStock`、`fetchPrices`、`fetchInstitutional`、`fetchMargin`、`fetchShareholding`、`fetchForeignHolding`。
   - `fetchStock` 或 `fetchPrices` 失敗 → 照 M1 顯示 `role="alert"` 錯誤。
   - 其他四個失敗 → **只 `console.warn`，狀態設成空陣列**，頁面照常顯示（籌碼表可能還沒回補）。
   - 籌碼的 `from` 與 K 線用同一個 `fromStr`；`fetchShareholding` 不帶 `from`（改帶 `limit: 104`）。
   - 沿用 M1 的 `reqIdRef` 請求序號與 `AbortController`。
4. **`tab === 'chart'`** → `<ChartStack bars={prices} institutional={institutional} margin={margin} showInstitutional={…} showMargin={…} />`；
   **`tab === 'chip'`** → `<ChipTab bars={prices} institutional={institutional} shareholding={shareholding} foreignHolding={foreignHolding} />`。
5. **U-10 註記**：`stock.market === 'TPEx'` 時，「還原價」label 後面加
   `<span className="hint">（上櫃除權息尚未收錄，還原價等同原始價）</span>`。
6. 沒有日 K 時照 M1 顯示「這檔目前沒有日 K 資料，請先執行回補。」

### 7. `web/src/styles.css`

新增（沿用既有的扁平寫法，不要引入 CSS 變數或框架）：
`.chart-stack`、`.chart-pane`、`.chart-pane-main`、`.chart-pane-title`（0.75rem 灰字）、
`.chart-readout`（`display:flex; flex-wrap:wrap; gap:0.75rem 1.25rem;` 小字，每個項目 `白底 + 1px 邊框 + 圓角`）、
`.chip-section`、`.chip-metric`（大字）、`.chip-table`（表格框線、右對齊數字）、`.hint`（0.8rem 灰字）、
`[role="tablist"]` 與 `[role="tab"][aria-selected="true"]`（底線標示目前分頁）。
`main` 的 `max-width` 從 `720px` 放寬到 `1080px`（副圖疊起來後 720px 太窄）。

### 8. 測試

#### 8.1 `src/chartSync.test.ts`（純函式，不需要 mock 圖表）

用假 pane：`{ id, chart: { setCrosshairPosition: vi.fn(), clearCrosshairPosition: vi.fn() }, series: {} as any, valueByTime: new Map([...]) }`

1. `test 其他 pane 收到 setCrosshairPosition`：三個 pane，`applyCrosshairToOthers(panes, 'main', '2026-09-18')` → pane2、pane3 的 `setCrosshairPosition` 各被呼叫一次，第一個參數是該 pane `valueByTime` 的值、第二個是 `'2026-09-18'`、第三個是該 pane 的 series。
2. `test 來源 pane 自己不會被設定`：pane1 的 `setCrosshairPosition` 沒被呼叫。
3. `test time 為 null 時全部 clear`。
4. `test 某個 pane 沒有那天的資料時只 clear 它`。
5. `test crosshairTime`：`{time:'2026-09-18'}` → `'2026-09-18'`；`{}` → `null`；`{time: 1758153600}` → `null`。

#### 8.2 `src/chipMath.test.ts`

6. `consecutiveDays([5000000, 8000000, 12000000])` → `{days:3, direction:'buy'}`
7. `consecutiveDays([1000000, -2000000, 2000000])` → `{days:1, direction:'buy'}`
8. `consecutiveDays([-300000, 200000, -500000])` → `{days:1, direction:'sell'}`
9. `consecutiveDays([])` 與 `consecutiveDays([1, 0])` → `{days:0, direction:'none'}`
10. `toLots(20200000) === '20,200'`、`toLots(null) === '—'`、`toPercent(70) === '70.00%'`、`toPercent(null) === '—'`

#### 8.3 `src/components/ChartStack.test.tsx`（**M2 完成標準的可執行版本**）

mock 要能「抓到 crosshair handler」。**`vi.mock` 會被提升到檔案最上面，所以共享陣列一定要用 `vi.hoisted` 宣告**，否則會踩到 TDZ 錯誤：

```ts
const { charts } = vi.hoisted(() => ({ charts: [] as any[] }))

vi.mock('lightweight-charts', () => {
  const makeSeries = () => ({
    setData: vi.fn(),
    applyOptions: vi.fn(),
    priceScale: () => ({ applyOptions: vi.fn() }),
  })
  return {
    createChart: vi.fn(() => {
      const timeScale = {
        fitContent: vi.fn(),
        applyOptions: vi.fn(),
        subscribeVisibleLogicalRangeChange: vi.fn(),
        unsubscribeVisibleLogicalRangeChange: vi.fn(),
        setVisibleLogicalRange: vi.fn(),
        getVisibleLogicalRange: vi.fn(() => null),
      }
      const chart: any = {
        addCandlestickSeries: vi.fn(() => makeSeries()),
        addLineSeries: vi.fn(() => makeSeries()),
        addHistogramSeries: vi.fn(() => makeSeries()),
        removeSeries: vi.fn(),
        timeScale: () => timeScale,
        priceScale: () => ({ applyOptions: vi.fn(), width: () => 72 }),
        applyOptions: vi.fn(),
        subscribeCrosshairMove: vi.fn((h: any) => { chart.__crosshair = h }),
        unsubscribeCrosshairMove: vi.fn(),
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
        resize: vi.fn(),
        remove: vi.fn(),
        __crosshair: null,
      }
      charts.push(chart)
      return chart
    }),
    ColorType: { Solid: 'solid' },
    CrosshairMode: { Normal: 0, Magnet: 1 },
    LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
  }
})

beforeEach(() => { charts.length = 0; vi.clearAllMocks() })
```

測試資料：三天 `2026-09-16/17/18`，`bars` 用 M1 fixture 的 `2330` 數字，
`institutional` 的 `total_net` 用 `[5700000, 6200000, 13500000]`、`foreign_net` 用 `[5000000, 8000000, 12000000]`，
`margin` 的 `margin_balance` 用 `[19500000, 20000000, 20200000]`、`short_balance` 用 `[900000, 1000000, 1090000]`。

11. `test 四個開關全開時建立四張圖`：`charts.length === 4`。
12. `test 每張圖都訂閱十字線`：每個 `chart.subscribeCrosshairMove` 都被呼叫過，且 `chart.__crosshair` 是函式。
13. **`test 主圖十字線會同步到其他三個 pane`**：呼叫 `charts[0].__crosshair({ time: '2026-09-18', point: { x: 10, y: 20 }, seriesData: new Map() })` →
    `charts[1].setCrosshairPosition`、`charts[2].setCrosshairPosition`、`charts[3].setCrosshairPosition` 各被呼叫一次，
    且第二個參數都是 `'2026-09-18'`；`charts[0].setCrosshairPosition` **沒有**被呼叫。
14. **`test 副圖十字線也會同步回主圖`**：呼叫 `charts[2].__crosshair({ time: '2026-09-17' })` → `charts[0].setCrosshairPosition` 被呼叫，第二參數 `'2026-09-17'`。
15. `test 滑鼠移出時清掉十字線`：`charts[0].__crosshair({})` → 其他三張的 `clearCrosshairPosition` 都被呼叫。
16. **`test 讀數面板跟著十字線換日期`**：初始 `readout-date` 是 `2026-09-18`；
    呼叫 `charts[0].__crosshair({ time: '2026-09-16' })` 後（包在 `act()` 裡），
    `readout-date` 變成 `2026-09-16`、`readout-foreign` 變成 `5,000`、`readout-margin` 變成 `19,500`。
17. `test 關掉兩個副圖只建兩張圖`：`showInstitutional={false} showMargin={false}` → `charts.length === 2`。
18. `test bars 為空時不建圖`：`charts.length === 0`，且不丟例外。

#### 8.4 `src/components/ChipTab.test.tsx`

19. `chip-big-ratio` 顯示 `80.00%`、`chip-retail-ratio` 顯示 `20.00%`、`chip-week` 含 `2026-09-18`。
20. 級距表有 7 列（level 1–15 中 fixture 有的七個），且 `level 15` 那列的人數是 `1,500`。
21. `chip-streak-foreign` 顯示「連買 3 天」、`chip-streak-dealer` 顯示「連賣 1 天」。
22. `chip-foreign-ratio` 顯示 `70.00%`。
23. 四份資料都是空陣列時，三個區塊各顯示對應的「尚無…」訊息，且不丟例外。

#### 8.5 `src/pages/StockPage.test.tsx`（改寫）

沿用 M1 的 `globalThis.fetch` mock 作法，依 URL 分派六個回應；lightweight-charts 用 §8.3 的同一份 mock。

24. `test 預設顯示 K 線分頁與讀數面板`。
25. `test 點「籌碼」分頁會顯示大戶比例`。
26. `test 會呼叫四個籌碼端點`：fetch 呼叫過含 `/institutional`、`/margin`、`/shareholding`、`/foreign-holding` 的 URL 各至少一次。
27. `test 籌碼端點回 500 時頁面仍然顯示 K 線`（只有 `/institutional` 回 500）：不出現 `role="alert"`，且 `readout-date` 還在。
28. `test 上櫃個股顯示還原價註記`：`market: 'TPEx'` → 畫面出現「上櫃除權息尚未收錄」。
29. M1 既有的四個測試（標頭數值、5Y 按鈕、500 錯誤、adj=false、count:0 無資料）維持通過，必要時只改選取器，**不要刪掉**。

### 驗收指令

```bash
cd /home/claude/TwStock/web && rm -rf node_modules && npm install && npm test && npm run build
# 預期：測試全部 passed（M1 的 23 個 + 本任務新增的約 19 個）；tsc 零錯誤；vite build 成功

cd /home/claude/TwStock/web && npx vitest run src/chartSync.test.ts src/components/ChartStack.test.tsx
# 預期：全部 passed —— 這兩支就是「副圖與主圖十字線同步」的完成標準

cd /home/claude/TwStock && scripts/m2_verify.sh | tail -1
# 預期：M2 VERIFY PASSED（回歸）

cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
# 預期：後端測試全部仍通過（回歸）

cd /home/claude/TwStock && docker compose -f deploy/docker-compose.yml --env-file .env.example config --quiet && echo COMPOSE_OK
# 預期：COMPOSE_OK
```

### 不要做的事

- 不要用 v5 API（`chart.addSeries(CandlestickSeries, …)`、`chart.addPane()` 都不存在於 4.2.3）。
- 不要在 jsdom 測試裡真的建立圖表（一定要 `vi.mock`），也不要用 `vi.mock` 之外的方式共享 `charts` 陣列（一定要 `vi.hoisted`）。
- 不要做三大法人堆疊柱（D-039），不要做 KD／MACD／RSI／布林通道（M3）。
- 不要做週 K／月 K 切換、自選股、排行、選股器、ETL 手動重跑。
- 不要新增或升級任何 npm 套件（含 `react-router-dom`、`vite`；U-13 留到 M3）。
- 不要改 `web/vite.config.ts`、`web/Dockerfile`、`deploy/docker-compose.yml`。
- 不要把籌碼資料補 0 對齊 K 線（沒有就不畫那一天）。

---

## 6. M2 的範圍邊界（全域，D-029）

**做**：三大法人（上市＋上櫃）、融資融券（上市＋上櫃）、借券賣出（上市）、外資持股（上市）、集保股權分散（全市場，每週）、
籌碼回補（除集保外）、四個籌碼 API、個股頁副圖與十字線同步、籌碼分頁、每日與每週排程，
以及 M1 技術債 U-9／U-12／U-14。

**不做**（寫在這裡是為了讓 Coder 不要自行發揮）：

| 項目 | 理由 | 留到 |
| --- | --- | --- |
| 上櫃借券、上櫃外資持股 | 官方端點不確定，M2 已經有五個新來源要驗 | M3 |
| 上櫃除權息（U-10，因此上櫃還原 K 線＝原始 K 線） | 需要新來源與還原係數重算；M2 只在前端加註記 | M3 |
| 集保的歷史回補 | 官方只留最新一週，不存在 | 永遠不做 |
| 三大法人堆疊柱（改為合計柱＋讀數面板） | Lightweight Charts 的 histogram 畫不出正負混合堆疊（D-039） | M3 |
| 分點進出、法人連續買賣天數的後端物化 | 前端用既有資料算就夠 | M3 之後 |
| 週 K／月 K（continuous aggregate 或 `freq` 參數） | 需要先確認 hypertable 真的建得起來（V-1） | M3 |
| KD／MACD／RSI／布林通道 | 前端計算，與籌碼無關 | M3 |
| ETL 手動重跑（寫入型 API） | M2 不做任何寫入型端點 | M3 |
| 月營收、財報、股利、估值、自選股、排行、選股器 | — | M3 |
| npm 相依升級（U-13） | 升 `react-router-dom` 7.18 有破壞性變更，不要跟籌碼混在同一個里程碑 | M3 |
| Redis 快取、Helm chart | — | 之後 |

## 7. 留待使用者本機驗證（本環境做不到）

本環境連不到 TWSE／TPEx／TDCC，也無法 build 映像。以下全部未實跑：

| # | 項目 | 指令 / 方式 | 通過標準 |
| --- | --- | --- | --- |
| V-9 | 上市三大法人真實格式（S1） | `python -m twstock_etl.cli load-chip --kind institutional --market TWSE --date <最近交易日>` | `rows` 約 1,000–1,100，無 `SourceFormatError` |
| V-10 | **上櫃三大法人真實格式（S2／S3，風險最高）** | `… --kind institutional --market TPEx --date <最近交易日>` | `rows` 約 800+；新版失敗會自動退回舊版並留 warning |
| V-11 | 上市融資融券真實格式（S4） | `… --kind margin --market TWSE --date <最近交易日>` | `rows` 約 1,000+ |
| V-12 | 上櫃融資融券真實格式（S5／S6） | `… --kind margin --market TPEx --date <最近交易日>` | `rows` 約 700+ |
| V-13 | **融資融券單位是「張」的假設（D-036）** | 回補一天後 `SELECT margin_balance FROM margin_daily WHERE stock_id='2330' AND trade_date='<該日>'`，與券商軟體／官方網頁上的「融資餘額（張）」比對 | DB 的值 ＝ 網頁的張數 × 1000。**若不符就是 parser 要改，不是資料錯** |
| V-14 | 借券賣出真實格式與單位（S7） | `… --kind sbl --market TWSE --date <最近交易日>`，再比對 `sbl_balance` 與官方「借券賣出當日餘額」 | 數量級相符（股，不是張） |
| V-15 | 外資持股真實格式（S8） | `… --kind foreign --market TWSE --date <最近交易日>`，比對 `2330` 的 `holding_ratio` 與官方公布的持股比率 | 差異只在四捨五入 |
| V-16 | **集保 CSV 真實格式與欄位名（S9）** | 週六 `python -m twstock_etl.cli load-shareholding` | `rows` 約 30,000+（2,000 檔 × 15–17 級）；`week_date` 是上一個週五。**若表頭欄位名與規格不符，把真實 CSV 前 30 行存成新 fixture 回報 Architect** |
| V-17 | 籌碼 5 年回補實跑與限流 | `python -m twstock_etl.cli backfill chip --kind institutional --market TWSE --from <5 年前> --to <今天>`（四類各跑一次） | 每步可 Ctrl-C 續跑；`--sleep 3` 下每類約 1 小時；沒有被擋 IP |
| V-18 | **瀏覽器目視：副圖與主圖十字線同步** | 開 `http://localhost:8080/stock/2330`，滑鼠在主圖上移動 | 成交量／法人／融資券三個副圖的十字線與主圖同一條垂直線；上方讀數面板的日期與數字跟著換；切到「籌碼」分頁看得到大戶比例與連買天數 |
| V-19 | 備份腳本可用且能還原 | `scripts/backup.sh`，再 `pg_restore --clean --if-exists --no-owner -d "$PG_URL" <dump>` 到一個空庫 | `BACKUP OK`；還原後 `SELECT count(*) FROM daily_price` 與原庫相同 |
| V-20 | 四張新表的 hypertable | `docker compose … exec db psql -c "SELECT hypertable_name FROM timescaledb_information.hypertables"` | 看得到 `institutional_daily`、`margin_daily`、`foreign_holding`、`shareholding_dist`（加上 M1 的兩張） |

**若真實格式與 fixture 不符**：把真實回應存進 `etl/tests/fixtures/`（檔名照現有慣例）、調整 parser 的 `find_field_all` 關鍵字、在 `docs/decisions.md` 補記，然後重跑 `scripts/m2_verify.sh`。
所有 parser 都有欄位硬檢查，不符會拋 `SourceFormatError` 而不是猜，**不會寫出錯誤數字**。

M1 的 V-1 ～ V-8 若仍未回報，不影響 M2 的本環境驗收，但**在使用者跑真實回補之前都還是未解**。

## 8. M1 未解問題在 M2 的處理

| # | M1 問題 | M2 處理 |
| --- | --- | --- |
| U-8 | 搜尋沒有模糊比對與索引（M0 留下） | 仍不處理，M3 再評估 |
| U-9 | `scripts/` 沒打包進 `twstock-etl` 映像 | **T2-1 解決**：回補收進 `python -m twstock_etl.cli backfill …`，`etl/Dockerfile` 也加 `COPY scripts`，兩條路都通（D-030） |
| U-10 | 上櫃除權息不在範圍，上櫃還原 K 線＝原始 K 線 | **不在 M2 範圍**（D-029），但 T2-8 在還原價開關旁加註記，使用者不會誤以為壞掉 |
| U-11 | `m1_verify.sh` 的斷點續傳只驗 TWSE 日 K | **T2-7 部分解決**：`m2_verify.sh` 的 `resume check` 另外驗 `backfill chip` 與 `load-shareholding` 兩條續傳路徑 |
| U-12 | 沒有備份腳本 | **T2-1 解決**：`scripts/backup.sh`（`pg_dump -Fc`、保留 7 份），還原步驟寫在檔頭與 V-19（D-032） |
| U-13 | 前端相依有 npm audit 警告 | **不在 M2 範圍**：`react-router-dom` 7.18 有破壞性變更，與籌碼混在一起會讓審查失焦，M3 單獨做一個升級任務 |
| U-14 | `daily_price` 沒有 `(stock_id, trade_date DESC)` 索引 | **T2-1 解決**：migration `0003` 加索引；實際效益要等 V-6 的真實資料量才量得到（D-031） |

## 任務狀態

| 任務 | 標題 | 相依 | 狀態 | 審查報告 |
| --- | --- | --- | --- | --- |
| T2-1 | 技術債：回補收進 CLI（U-9）、`daily_price` 索引（U-14）、備份腳本（U-12） | — | DONE | [T2-1](../reviews/T2-1.md) |
| T2-2 | Migration 0004：籌碼四表與 `models.py` 五個 dataclass | T2-1 | DONE | [T2-2](../reviews/T2-2.md) |
| T2-3 | 集保股權分散（TDCC）端到端：parser → loader → job → CLI → 每週排程 | T2-2 | DONE | [T2-3](../reviews/T2-3.md) |
| T2-4 | 來源 parser：三大法人（上市 T86、上櫃含舊版備援） | T2-2 | DONE | [T2-4](../reviews/T2-4.md) |
| T2-5 | 來源 parser：融資融券（上市／上櫃）、借券賣出、外資持股 | T2-4（共用 `find_field_all`） | DONE | [T2-5](../reviews/T2-5.md) |
| T2-6 | Loader、來源登錄表、統一 job／CLI／排程／回補 | T2-4、T2-5 | DONE | — |
| T2-7 | API：四個籌碼端點，與後端整合驗收腳本 | T2-3、T2-6 | DONE | [T2-7](../reviews/T2-7.md) |
| T2-8 | 前端：副圖與主圖十字線同步、籌碼分頁 | T2-7 | TODO | — |

狀態語意固定四種（D-027）：`TODO`（沒做）、`IN_REVIEW`（程式已在 `main`／已回報，等待審查）、
`DONE`（審查通過，且 `docs/reviews/<任務>.md` 存在）、`BLOCKED`（**只有** Reviewer 實際出具 REQUEST_CHANGES 報告後才能標）。
沒有審查報告就不准標 BLOCKED；Coder 不得 commit，審查報告一律由 Reviewer 寫。

> **T2-3 完成後的提醒（Architect 在該任務驗收時要主動講）**：集保開放資料只留最新一週，
> 請使用者立刻在 Mac 上把 `etl` 排程跑起來（或每週六手動 `python -m twstock_etl.cli load-shareholding` 一次），
> 不要等 M2 全部做完——每漏一週就是一週永遠補不回來的歷史。
