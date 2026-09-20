# TwStock

個人台股查詢系統：每日盤後自動抓資料進資料庫，網頁查個股 K 線、籌碼、基本面。

- 設計計劃：[docs/plan.md](docs/plan.md)
- 專案規則與目錄說明：[CLAUDE.md](CLAUDE.md)

## 目前進度

**M0（骨架）已完成並通過里程碑驗收**（報告：[docs/reports/M0.md](docs/reports/M0.md)；規格：[docs/specs/M0-skeleton.md](docs/specs/M0-skeleton.md)）。

**M1（價格 + K 線）已完成並通過里程碑驗收**（規格：[docs/specs/M1-price.md](docs/specs/M1-price.md)；驗收：`scripts/m1_verify.sh`）。

目前可用的功能：

| 項目 | 狀態 |
| --- | --- |
| PostgreSQL（+TimescaleDB，若有）schema：`stock`、`trading_calendar`、`daily_price`、`index_daily`、`adj_factor`、`etl_job_log`，由 Alembic 管理 | 完成 |
| ETL：TWSE / TPEx 個股清單、日成交價格、加權指數、除權除息、排程、CLI、回補腳本 | 完成 |
| API：`GET /api/stocks`、`GET /api/stocks/{id}`、`GET /api/stocks/{id}/prices`、`GET /api/indices/{id}/prices`、`GET /api/etl/jobs`、`GET /api/etl/summary` | 完成 |
| Web：搜尋頁、個股 K 線頁（還原價開關、區間切換、MA、成交量）、ETL 狀態頁（維運用） | 完成 |
| Docker Compose：`db` / `migrate` / `api` / `etl` / `web` 五個 service | 完成 |
| 法人買賣超、集保分布、財報、營收趨勢 | 尚未開始（M2 之後） |

M1 新增功能說明：
- 個股頁 `/stock/:id`：K 線圖（最新 1 年，支援 3M / 6M / 1Y / 3Y / 5Y 區間切換）、MA5/20/60 均線、成交量副圖、還原價開關（切換後自動重新載入資料）。
- ETL 狀態頁 `/admin/etl`：監看 ETL job 執行紀錄，可手動刷新。
- 回補腳本 `scripts/backfill.py`：支援離線模式（用 fixture 快速測試），斷點續傳，進度輸出。

## 本機啟動方式（macOS，Docker）

需要 Docker Desktop（含 Docker Compose v2）。以下指令都在 repo 根目錄執行。

### 1. 建立 `.env`

```bash
cp .env.example .env
```

用編輯器打開 `.env`，**至少要改 `POSTGRES_PASSWORD`**（compose 檔沒有預設值，留空會直接啟動失敗）：

| 變數 | 說明 | 建議值 |
| --- | --- | --- |
| `POSTGRES_USER` | DB 帳號 | `twstock`（預設即可） |
| `POSTGRES_PASSWORD` | DB 密碼，**必填** | 自行設定一組長密碼 |
| `POSTGRES_DB` | 資料庫名稱 | `twstock`（預設即可） |
| `TZ` | 容器時區 | `Asia/Taipei` |
| `DATABASE_URL` | **只有「本機開發（無 Docker）」時才用到**；Docker 內的連線字串由 compose 自動組出（連到 `db:5432`），不需要改這一行 | — |
| `FINMIND_TOKEN` | M2 之後才會用到，M0 可留空 | 空白 |

`.env` 已在 `.gitignore`，不會進版控。

### 2. 啟動

```bash
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
```

首次執行會下載映像（`timescale/timescaledb:2.21.3-pg16`、`python:3.12-slim-bookworm`、`node:22-alpine`、`nginx:1.27-alpine`）並建置三個自家映像，依網速約需 5～15 分鐘。

啟動順序由 compose 控制：`db` 健康檢查通過 → `migrate` 跑完 Alembic 後結束（exit 0 是正常的）→ `api`、`etl`、`web` 啟動。

`etl` 是常駐排程器，**啟動當下會立刻跑一次**個股清單（TWSE + TPEx）與今年交易日曆，之後每天台北時間 07:30 更新日曆、08:00 更新個股清單。首次抓取約 1～2 分鐘。

### 3. 使用

- 網頁：<http://localhost:8080>
- API：<http://localhost:8000/api/health>、<http://localhost:8000/api/stocks?q=2330>
- DB（可用 psql / TablePlus 連）：`localhost:5432`，帳密即 `.env` 內設定

三個 port 都只綁在 `127.0.0.1`，不會對外網開放。

### 4. 常用維運指令

```bash
# 看 ETL 抓取進度
docker compose -f deploy/docker-compose.yml logs -f etl

# 確認 migrate 有跑完
docker compose -f deploy/docker-compose.yml logs migrate

# 確認 TimescaleDB 擴充已安裝
docker compose -f deploy/docker-compose.yml exec db psql -U twstock -d twstock -c '\dx'

# 看載入了幾檔
docker compose -f deploy/docker-compose.yml exec db \
  psql -U twstock -d twstock -c "SELECT market, count(*) FROM stock GROUP BY market;"

# 停止（保留資料）
docker compose -f deploy/docker-compose.yml down

# 停止並刪除資料庫磁碟區（資料全清）
docker compose -f deploy/docker-compose.yml down -v
```

### 5. 手動以真實來源載入個股清單

平時不需要手動跑（`etl` 排程器會自己更新）。要立刻重抓一次時，在 `etl` 容器內執行 CLI：

```bash
# 上市（TWSE，來源 https://isin.twse.com.tw/isin/C_public.jsp?strMode=2）
docker compose -f deploy/docker-compose.yml exec etl \
  python -m twstock_etl.cli load-stocks --market TWSE

# 上櫃（TPEx，來源 https://isin.twse.com.tw/isin/C_public.jsp?strMode=4）
docker compose -f deploy/docker-compose.yml exec etl \
  python -m twstock_etl.cli load-stocks --market TPEx

# 交易日曆（來源 TWSE OpenAPI holidaySchedule，預設抓台北時間今年）
docker compose -f deploy/docker-compose.yml exec etl \
  python -m twstock_etl.cli load-calendar
```

輸出範例：`loaded market=TWSE records=1043 deactivated=0`。合理範圍是上市約 1,000+ 筆、上櫃約 800+ 筆（股票 + ETF，不含權證、特別股、TDR、興櫃）。

其他選項：

- `--deactivate-missing`：把「這次清單中已消失」的個股標成 `is_active=false`（下市處理）。排程器每日自動帶這個旗標；手動執行預設不帶，較安全。有保護機制：若這次解析出的筆數少於 500（`twstock_etl.jobs.MIN_RECORDS_FOR_DEACTIVATE`），會直接丟 `SourceFormatError` 拒絕停用，避免來源異常時把整個市場誤停用。
- `--year 2027`：指定交易日曆年份。
- `--file <路徑>`：改讀本機檔案而非連網（ISIN 為 UTF-8 HTML、日曆為 JSON），用於離線測試。

若首次執行就噴 `SourceFormatError`，代表官方頁面格式與 parser 預期不符，請把實際回應存檔後更新 `etl/tests/fixtures/` 與 `etl/twstock_etl/sources/`，並在 `docs/decisions.md` 補記。

### 6. 歷史回補（5年資料）

初次開發或環境重建時，需要補回 5 年的歷史數據。`scripts/backfill.py` 提供四個子指令：

```bash
# 查看用法
scripts/backfill.py --help

# 建議的執行順序：

# 1. 先載入個股清單（見上方第 5 節）
.venv/bin/python -m twstock_etl.cli load-stocks --market TWSE
.venv/bin/python -m twstock_etl.cli load-stocks --market TPEx

# 2. 加權指數月度資料（約 60 次 API 請求，預設 3 秒延遲）
.venv/bin/python scripts/backfill.py index --from 2021-01 --to 2026-09

# 3. 反推交易日曆（無 API 請求，用指數日期推算）
.venv/bin/python scripts/backfill.py calendar --from-year 2021 --to-year 2025

# 4. 上市個股日 K（TWSE，約 1,200 次 API 請求，預設約需 1 小時）
.venv/bin/python scripts/backfill.py price --market TWSE --from 2021-01-04 --to 2026-09-18

# 5. 上櫃個股日 K（TPEx，約 1,200 次 API 請求，預設約需 1 小時）
.venv/bin/python scripts/backfill.py price --market TPEx --from 2021-01-04 --to 2026-09-18

# 6. 除權息資料（約每個月 1 次 API 請求）
.venv/bin/python scripts/backfill.py exright --from 2021-01-01 --to 2026-09-18
```

各指令支援以下選項：

- `--sleep SECONDS`：兩次 API 請求間隔（預設 3.0 秒）
- `--max-failures N`：容許最多失敗次數，超過即中止（預設 10）
- `--force`：強制重新抓取，不使用斷點續傳（預設優先跳過已完成日期）
- `--source-dir PATH`：離線模式，從目錄讀 JSON 檔案而不發 HTTP 請求（用於開發測試）
- `--dry-run`：只印執行計畫，不寫 DB、不發 HTTP

任何時候都可以按 Ctrl-C 中斷，重新執行時會自動從中斷處繼續（用 `etl_job_log` 表追蹤進度）。

## 本機開發（無 Docker）

需要 Python 3.11+、PostgreSQL 16、Node 22。

```bash
# 1. 虛擬環境與依賴
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# 2. 臨時資料庫（會印出連線字串）
scripts/pg_temp.sh start
export DATABASE_URL="postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test"
.venv/bin/alembic -c db/alembic.ini upgrade head

# 3. 載入資料
#    離線（用 fixture 樣本，17 檔）：
.venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html
.venv/bin/python -m twstock_etl.cli load-stocks --market TPEx --file etl/tests/fixtures/isin_tpex_strmode4.html
.venv/bin/python -m twstock_etl.cli load-calendar --year 2026 --file etl/tests/fixtures/twse_holiday_schedule_2026.json
#    連網（真實來源，全部個股）：把上面三行的 --file / --year 拿掉即可

# 4. 啟動 API（另開終端機，同樣要 export DATABASE_URL）
.venv/bin/uvicorn twstock_api.main:app --host 127.0.0.1 --port 8000

# 5. 啟動前端開發伺服器（另開終端機；Vite 已設定 proxy 到 8000）
cd web && npm install && npm run dev
# 開 http://localhost:5173
```

停止資料庫：`scripts/pg_temp.sh stop`；清空重來：`scripts/pg_temp.sh reset`。

## 測試

```bash
# 後端（不設 TWSTOCK_TEST_DATABASE_URL 時，需要 DB 的測試會 skip 而不是 fail）
TWSTOCK_TEST_DATABASE_URL="$(scripts/pg_temp.sh start)" .venv/bin/python -m pytest

# 前端
cd web && npm test && npm run build

# M0 整合驗收（自建臨時 DB → migration → 載入 fixture → 起 API → 逐檔驗證可搜尋）
scripts/m0_verify.sh   # 成功時最後一行為 M0 VERIFY PASSED

# M1 整合驗收（自建臨時 DB → migration → 以 fixture 離線回補 → 起 API → 驗證 M1 數值）
scripts/m1_verify.sh   # 成功時最後一行為 M1 VERIFY PASSED

# Docker Compose 設定語法檢查（不會真的啟動）
docker compose -f deploy/docker-compose.yml --env-file .env.example config --quiet
```
