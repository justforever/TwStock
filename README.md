# TwStock

個人台股查詢系統：每日盤後自動抓資料進資料庫，網頁查個股 K 線、籌碼、基本面。

- 設計計劃：[docs/plan.md](docs/plan.md)
- 專案規則與目錄說明：[CLAUDE.md](CLAUDE.md)

## 目前進度

**M0（骨架）已完成並通過里程碑驗收**（報告：[docs/reports/M0.md](docs/reports/M0.md)；規格：[docs/specs/M0-skeleton.md](docs/specs/M0-skeleton.md)）。

**M1（價格 + K 線）已完成並通過里程碑驗收**（2026-09-21；規格：[docs/specs/M1-price.md](docs/specs/M1-price.md)；驗收報告：[docs/reports/M1.md](docs/reports/M1.md)；驗收腳本：`scripts/m1_verify.sh`）。

驗收在開發環境以離線 fixture 跑完整條路徑（臨時 PostgreSQL → migration → 回補 → API → 數值核對）。**真實來源連線、`docker compose up --build`、TimescaleDB hypertable、5 年回補實跑只能在你的 Mac 上驗證**，逐項清單見 [docs/reports/M1.md](docs/reports/M1.md)「只能在 Mac 上驗證的項目」與規格 §7。

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

- `--deactivate-missing`：把「這次清單中已消失」的個股標成 `is_active=false`（下市處理）。排程器每日自動帶這個旗標；手動執行預設不帶，較安全。有保護機制：若這次解析出的筆數不到「該市場目前有效檔數」的 70%（`twstock_etl.jobs.DEACTIVATE_MIN_RATIO`），會直接丟 `SourceFormatError` 拒絕停用，避免來源回傳不完整頁面時把整個市場誤停用（見 `docs/decisions.md` D-020）。
- `--year 2027`：指定交易日曆年份。
- `--file <路徑>`：改讀本機檔案而非連網（ISIN 為 UTF-8 HTML、日曆為 JSON），用於離線測試。

若首次執行就噴 `SourceFormatError`，代表官方頁面格式與 parser 預期不符，請把實際回應存檔後更新 `etl/tests/fixtures/` 與 `etl/twstock_etl/sources/`，並在 `docs/decisions.md` 補記。

### 6. 歷史回補（5 年資料）——在 Mac 上怎麼跑

初次建置或環境重建時要補回 5 年歷史。回補全部由 `scripts/backfill.py` 完成（四個子指令：`index`、`calendar`、`price`、`exright`）。

#### 6.1 前置條件

1. DB 已啟動、`migrate` 已跑完（`docker compose … logs migrate` 看得到 `upgrade head`）。
2. **個股清單已載入**（第 5 節）。日 K 寫入時會用 `stock` 表過濾未知代號，清單沒載會整批被丟掉（`rows=0`）。
3. **`scripts/` 沒有打包進 `twstock-etl` 映像**（映像只裝 `db/`、`etl/` 兩個套件），所以回補腳本不能用 `docker compose exec etl python scripts/backfill.py`。用下面兩種方式之一：

**做法 A（建議）：在 Mac 上用 venv 跑，連 compose 的 DB**

```bash
cd ~/path/to/TwStock
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
# 密碼用 .env 裡的 POSTGRES_PASSWORD；compose 已把 5432 綁在 127.0.0.1，host 連得到
export DATABASE_URL="postgresql+psycopg://twstock:<你的密碼>@127.0.0.1:5432/twstock"
.venv/bin/python scripts/backfill.py --help
```

**做法 B：不想在 Mac 裝 Python，就把 `scripts/` 掛進容器跑一次性任務**

```bash
docker compose -f deploy/docker-compose.yml --env-file .env run --rm \
  -v "$PWD/scripts:/app/scripts" etl \
  python /app/scripts/backfill.py price --market TWSE --from 2021-01-04 --to 2026-09-18
```

（`run --rm` 會沿用 `etl` service 的 `DATABASE_URL`，不必自己組連線字串。）

#### 6.2 執行順序與預估時間

順序不能換：日 K 只回補 `trading_calendar` 裡 `is_open=true` 的日期，而歷史年度的日曆是由加權指數反推出來的（見 `docs/decisions.md` D-021）。

| # | 指令（以 2021-01-04 ～ 2026-09-18 為例） | 請求數 | `--sleep 3` 預估 |
| --- | --- | --- | --- |
| 1 | `python -m twstock_etl.cli load-stocks --market TWSE` / `--market TPEx` | 2 | < 1 分鐘 |
| 2 | `python -m twstock_etl.cli load-calendar`（今年，官方休市日） | 1 | 數秒 |
| 3 | `scripts/backfill.py index --from 2021-01 --to 2026-09` | 約 69（每月 1 次） | 約 5 分鐘 |
| 4 | `scripts/backfill.py calendar --from-year 2021 --to-year 2025` | 0（用指數反推） | 數秒 |
| 5 | `scripts/backfill.py price --market TWSE --from 2021-01-04 --to 2026-09-18` | 約 1,220（每交易日 1 次） | 約 1～1.5 小時 |
| 6 | `scripts/backfill.py price --market TPEx --from 2021-01-04 --to 2026-09-18` | 約 1,220 | 約 1～1.5 小時 |
| 7 | `scripts/backfill.py exright --from 2021-01-01 --to 2026-09-18` | 約 69（每月 1 次） | 約 5 分鐘 |

**整趟約 3 小時**（`--sleep 3`，實際受來源回應速度影響）。完成後 `daily_price` 約 240 萬列（上市＋上櫃 × 5 年），連同索引大約佔 0.5～1 GB 磁碟。

`--sleep` 是禮貌性速率限制，不建議調到 1 秒以下；來源回 429 或連線被掐時反而更慢。

建議讓 Mac 不要睡著，並把輸出留成 log：

```bash
caffeinate -i .venv/bin/python scripts/backfill.py price --market TWSE \
  --from 2021-01-04 --to 2026-09-18 2>&1 | tee -a ~/twstock-backfill-TWSE.log
```

進度每個工作單位印一行：

```
[  12/1220] 2021-01-20 TWSE rows=1024 elapsed=00:00:38 eta=01:02:15
[  13/1220] 2021-01-21 TWSE skip 已完成
[  14/1220] 2021-01-22 TWSE FAIL 來源回應 stat 非 OK：很抱歉
完成 1180／跳過 38／失敗 2，共寫入 1203456 筆，耗時 01:07:42
```

#### 6.3 中斷與續傳

- **隨時可以 Ctrl-C**。腳本會印 `已中斷，下次執行會從 YYYY-MM-DD 繼續`（stderr），離開碼 `130`。
- **續傳就是把同一條指令再跑一次**，不必改參數。每個日期（或月份）成功後會在 `etl_job_log` 留一筆 `success`，重跑時以 `has_successful_run` 判斷並印 `skip 已完成`，不會重抓。
- 斷點以「job 單位」記錄，不是檔案位移，所以續跑時把 `--from` 往前拉、或整段重跑都沒關係，重疊的部分一律被 skip。
- 關機、睡眠、網路斷線、容器重啟都不影響續傳——狀態全在資料庫裡。
- 看目前進度：`http://localhost:8080/admin/etl`，或

```bash
docker compose -f deploy/docker-compose.yml exec db psql -U twstock -d twstock -c \
  "SELECT job_name, max(target_date) FILTER (WHERE status='success') AS 最新成功日
     FROM etl_job_log GROUP BY job_name ORDER BY job_name;"
```

#### 6.4 失敗了怎麼重來

| 狀況 | 現象 | 處理 |
| --- | --- | --- |
| 個別日期失敗 | 該行印 `FAIL …`，腳本繼續往下跑，結束時離開碼 `1` | **直接重跑同一條指令**。失敗的日期沒有 `success` 紀錄，會被重抓；成功的照樣 skip |
| 失敗次數超過 `--max-failures`（預設 10） | 印 `失敗次數超過 10，中止回補`，離開碼 `2` | 多半是來源改版或被限流。先 `--dry-run` 確認計畫，再用 `--sleep 6` 放慢重跑；若錯誤訊息是 `SourceFormatError`，把真實回應存成 `etl/tests/fixtures/` 的樣本、修 parser，並在 `docs/decisions.md` 補記（規格 §7） |
| 某年日 K「一下就跑完、total=0」 | 該年 `trading_calendar` 沒有開市日 | 先補該年的 `index`，再跑 `calendar --from-year … --to-year …`，然後重跑 `price` |
| `rows=0` 但沒有錯誤 | `stock` 表是空的或清單沒更新 | `SELECT count(*) FROM stock;` 應為 2,000+；否則先跑第 5 節的 `load-stocks` |
| 來源事後更正數字，要重抓已成功的日期 | — | 用 `--force` 搭配縮小的 `--from`/`--to` 區間重跑（`--force` 會忽略斷點，整段重抓） |
| 忘記設 `DATABASE_URL` | `錯誤：未設定 DATABASE_URL 環境變數`，離開碼 `1` | 照 6.1 `export` 後重跑 |

離開碼對照：`0` 全部完成、`1` 有失敗或參數／來源錯誤、`2` 超過 `--max-failures` 中止、`130` 被 Ctrl-C 中斷。

其他選項：`--sleep SECONDS`（請求間隔，預設 3.0）、`--max-failures N`（預設 10）、`--force`（忽略斷點重抓）、
`--source-dir PATH`（離線模式，改讀目錄下的 JSON，不發 HTTP，供測試用）、`--dry-run`（只印計畫，不寫 DB、不發 HTTP）。

#### 6.5 回補完成後的抽查

```bash
docker compose -f deploy/docker-compose.yml exec db psql -U twstock -d twstock -c \
  "SELECT source, count(*) AS 列數, min(trade_date), max(trade_date) FROM daily_price GROUP BY source;"
docker compose -f deploy/docker-compose.yml exec db psql -U twstock -d twstock -c \
  "SELECT count(*) FROM adj_factor;"
```

再開 <http://localhost:8080/stock/2330>，切到 5Y、勾「還原價」，和券商軟體或 FinMind 的還原價比對最近一次除權息前後（規格 §7 V-7）。

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
