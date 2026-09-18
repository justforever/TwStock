# TwStock

個人台股查詢系統：每日盤後自動抓資料進資料庫，網頁查個股 K 線、籌碼、基本面。

- 設計計劃：[docs/plan.md](docs/plan.md)
- 專案規則與目錄說明：[CLAUDE.md](CLAUDE.md)

## 目前進度

**M0（骨架）已完成並通過里程碑驗收**（報告：[docs/reports/M0.md](docs/reports/M0.md)；規格：[docs/specs/M0-skeleton.md](docs/specs/M0-skeleton.md)）。

目前可用的功能：

| 項目 | 狀態 |
| --- | --- |
| PostgreSQL（+TimescaleDB，若有）schema：`stock`、`trading_calendar`，由 Alembic 管理 | 完成 |
| ETL：TWSE / TPEx 個股清單（ISIN 一覽表）、TWSE 休市日與交易日曆、冪等寫入、CLI、APScheduler 每日排程 | 完成 |
| API：`GET /api/stocks?q=`（代號前綴／名稱包含、臺台互通）、`GET /api/health` | 完成 |
| Web：React + Vite 搜尋頁（防抖、`/` 快捷鍵、`/stock/:id` 占位頁） | 完成 |
| Docker Compose：`db` / `migrate` / `api` / `etl` / `web` 五個 service | 完成 |
| 日 K 線、法人買賣超、集保分布、財報 | 尚未開始（M1 之後） |

尚未做的事：`daily_price` 等時序表。個股清單（TWSE/TPEx ISIN）真實來源已驗證通過（見 [docs/reports/M0.md](docs/reports/M0.md)「未解問題」U-1）；TDCC/MOPS/FinMind 尚未驗證。

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
cd web && npm test

# M0 整合驗收（自建臨時 DB → migration → 載入 fixture → 起 API → 逐檔驗證可搜尋）
scripts/m0_verify.sh   # 成功時最後一行為 M0 VERIFY PASSED

# Docker Compose 設定語法檢查（不會真的啟動）
docker compose -f deploy/docker-compose.yml --env-file .env.example config --quiet
```
