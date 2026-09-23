# TwStock

個人台股查詢系統：每日盤後自動抓資料進資料庫，網頁查個股 K 線、籌碼、基本面。

- 設計計劃：[docs/plan.md](docs/plan.md)
- 專案規則與目錄說明：[CLAUDE.md](CLAUDE.md)

## 目前進度

**M0（骨架）已完成並通過里程碑驗收**（報告：[docs/reports/M0.md](docs/reports/M0.md)；規格：[docs/specs/M0-skeleton.md](docs/specs/M0-skeleton.md)）。

**M1（價格 + K 線）已完成並通過里程碑驗收**（2026-09-21；規格：[docs/specs/M1-price.md](docs/specs/M1-price.md)；驗收報告：[docs/reports/M1.md](docs/reports/M1.md)；驗收腳本：`scripts/m1_verify.sh`）。

**M2（籌碼）已完成並通過里程碑驗收**（2026-09-21；規格：[docs/specs/M2-chips.md](docs/specs/M2-chips.md)；驗收報告：[docs/reports/M2.md](docs/reports/M2.md)；驗收腳本：`scripts/m2_verify.sh`）。

驗收在開發環境以離線 fixture 跑完整條路徑（臨時 PostgreSQL → migration → 回補 → API → 數值核對）。**真實來源連線、`docker compose up --build`、TimescaleDB hypertable、5 年回補實跑、瀏覽器目視只能在你的 Mac 上驗證**，逐項清單見 [docs/reports/M2.md](docs/reports/M2.md)「只能在 Mac 上驗證的項目」（V-9 ～ V-20）與規格 §7。

> **M2 收尾後最該先做的一件事**：把 `etl` 排程器跑起來（或每週六手動跑一次 `load-shareholding`）。
> 集保股權分散官方只留最新一週，**漏抓就永遠補不回來**，詳見第 7.2 節。

目前可用的功能：

| 項目 | 狀態 |
| --- | --- |
| PostgreSQL（+TimescaleDB，若有）schema：`stock`、`trading_calendar`、`daily_price`、`index_daily`、`adj_factor`、`etl_job_log`，由 Alembic 管理 | 完成（M0／M1） |
| 籌碼 schema：`institutional_daily`、`margin_daily`、`foreign_holding`、`shareholding_dist` | 完成（M2） |
| ETL：TWSE / TPEx 個股清單、日成交價格、加權指數、除權除息、排程、CLI、回補 | 完成（M1） |
| ETL：三大法人（上市＋上櫃）、融資融券（上市＋上櫃）、借券賣出（上市）、外資持股（上市）、集保股權分散（全市場，每週） | 完成（M2） |
| API：`GET /api/stocks`、`/api/stocks/{id}`、`/api/stocks/{id}/prices`、`/api/indices/{id}/prices`、`/api/etl/jobs`、`/api/etl/summary` | 完成（M1） |
| API：`GET /api/stocks/{id}/institutional`、`/margin`、`/foreign-holding`、`/shareholding` | 完成（M2） |
| Web：搜尋頁、個股 K 線頁（還原價開關、區間切換、MA、成交量）、ETL 狀態頁（維運用） | 完成（M1） |
| Web：個股頁多 pane 副圖（成交量／三大法人／融資融券）與主圖十字線同步＋讀數面板、「籌碼」分頁（集保大戶比例、外資持股、法人連續買賣天數） | 完成（M2） |
| 備份腳本 `scripts/backup.sh`、`daily_price` 查詢索引、回補收進 CLI | 完成（M2，技術債 U-9／U-12／U-14） |
| 上櫃借券、上櫃外資持股、上櫃除權息、週 K／月 K、KD／MACD／RSI | 未開始（M3） |
| 月營收、財報、股利、估值、自選股、排行、選股器 | 未開始（M3 之後） |

M2 新增功能說明：
- 個股頁 `/stock/:id` 分成「K 線」與「籌碼」兩個分頁。K 線分頁是四個 pane（主圖 K 線＋成交量／三大法人買賣超／融資融券餘額三個副圖），**滑鼠移到哪一天，四張圖的十字線與上方讀數面板一起跳到那一天**。
- 籌碼分頁：集保大戶（400 張以上）比例趨勢、外資持股比例趨勢、三大法人連續買賣超天數。
- 上櫃個股的還原價開關旁有「上櫃除權息尚未收錄」註記（U-10 留到 M3），不會讓人誤以為還原價壞掉。
- 籌碼回補、集保每週載入的操作方式見第 7 節。

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

> **注意**：真正的 compose 設定放在 `deploy/docker-compose.yml`，但 Compose 預設抓 `.env` 的目錄是「compose 檔所在目錄」，不是你執行指令時的路徑，所以只在 repo 根目錄放 `.env` 是不夠的——沒帶 `--env-file` 的指令（例如 `logs`、`exec`、`down`）會抓不到密碼，出現 `required variable POSTGRES_PASSWORD is missing a value`。repo 根目錄已內建一個 `docker-compose.yml`（用 Compose 的 `include:` 接進 `deploy/docker-compose.yml`，見 D-043），下面的指令都改成不帶 `-f`／`--env-file` 直接在根目錄執行即可；舊的 `-f deploy/docker-compose.yml --env-file .env` 寫法也還能用，操作的是同一組容器。

### 2. 啟動

```bash
docker compose up -d --build
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
docker compose logs -f etl

# 確認 migrate 有跑完
docker compose logs migrate

# 確認 TimescaleDB 擴充已安裝
docker compose exec db psql -U twstock -d twstock -c '\dx'

# 看載入了幾檔
docker compose exec db \
  psql -U twstock -d twstock -c "SELECT market, count(*) FROM stock GROUP BY market;"

# 停止（保留資料）
docker compose down

# 停止並刪除資料庫磁碟區（資料全清）
docker compose down -v
```

### 5. 手動以真實來源載入個股清單

平時不需要手動跑（`etl` 排程器會自己更新）。要立刻重抓一次時，在 `etl` 容器內執行 CLI：

```bash
# 上市（TWSE，來源 https://isin.twse.com.tw/isin/C_public.jsp?strMode=2）
docker compose exec etl \
  python -m twstock_etl.cli load-stocks --market TWSE

# 上櫃（TPEx，來源 https://isin.twse.com.tw/isin/C_public.jsp?strMode=4）
docker compose exec etl \
  python -m twstock_etl.cli load-stocks --market TPEx

# 交易日曆（來源 TWSE OpenAPI holidaySchedule，預設抓台北時間今年）
docker compose exec etl \
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
docker compose run --rm \
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
docker compose exec db psql -U twstock -d twstock -c \
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
docker compose exec db psql -U twstock -d twstock -c \
  "SELECT source, count(*) AS 列數, min(trade_date), max(trade_date) FROM daily_price GROUP BY source;"
docker compose exec db psql -U twstock -d twstock -c \
  "SELECT count(*) FROM adj_factor;"
```

再開 <http://localhost:8080/stock/2330>，切到 5Y、勾「還原價」，和券商軟體或 FinMind 的還原價比對最近一次除權息前後（規格 §7 V-7）。

### 7. 籌碼資料怎麼載入（M2）

籌碼有兩種節奏，操作方式完全不同：

| 類型 | 頻率 | 有沒有歷史可補 | 指令 |
| --- | --- | --- | --- |
| 三大法人、融資融券、借券賣出、外資持股 | 每個交易日 | **有**，官方端點可帶日期查歷史 | `load-chip`（單日）／`backfill chip`（區間） |
| 集保股權分散（TDCC） | 每週（資料日期是週五） | **沒有，官方只留最新一週** | `load-shareholding`（只有「現在這一週」） |

#### 7.1 平時不用管：排程器會自己抓

`etl` service 起來之後，每天／每週會自己跑，時間都是台北時間。同一天重跑靠 `etl_job_log` 去重，所以一天排三個時段只是「第一次沒抓到就再試」，不會重複寫入：

| 資料 | `job_name` | 排程時間（台北） |
| --- | --- | --- |
| 上市三大法人 | `institutional_twse` | 16:30、18:30、20:30 |
| 上櫃三大法人 | `institutional_tpex` | 16:40、18:40、20:40 |
| 上市外資持股 | `foreign_holding_twse` | 17:00、19:00、21:00 |
| 上市融資融券 | `margin_twse` | 21:30、22:30、23:30 |
| 上櫃融資融券 | `margin_tpex` | 21:40、22:40、23:40 |
| 上市借券賣出 | `sbl_twse` | 21:50、22:50、23:50 |
| 集保股權分散 | `shareholding_tdcc` | **每週六、日 10:00 與 16:00**（一週共四次機會） |

融資融券排在晚上 21:30 之後，是因為官方的信用交易統計要等到當日盤後才更新完；法人資料下午就有了，所以排在 16:30。

看有沒有抓到：<http://localhost:8080/admin/etl>，或

```bash
docker compose exec db psql -U twstock -d twstock -c \
  "SELECT job_name, max(target_date) FILTER (WHERE status='success') AS 最新成功日, count(*) FILTER (WHERE status='failed') AS 失敗次數
     FROM etl_job_log
    WHERE job_name IN ('institutional_twse','institutional_tpex','margin_twse','margin_tpex','sbl_twse','foreign_holding_twse','shareholding_tdcc')
    GROUP BY job_name ORDER BY job_name;"
```

#### 7.2 集保每週排程要注意什麼（**最重要的一節**）

集保（TDCC）的股權分散表是整個專案裡唯一「漏抓就永遠補不回來」的資料：**官方開放資料只掛最新一週的檔案，上一週的檔案會直接被覆蓋掉**。所以：

1. **`etl` 排程器要一直開著**，或至少每個週末開一次。這件事不必等其他功能做完，現在就可以開始累積歷史。
2. 排程刻意排成**週六、週日各兩次（10:00、16:00）**，一週有四次機會。官方通常在週六上午更新上一個週五的資料，但偶爾會延到週日；四次機會是為了容忍延遲，不是要抓四份。
3. **同一週只會寫入一次**。job 的 `target_date` 不是執行日，而是**資料裡的週五日期**（解析完 CSV 才知道，見 `docs/decisions.md` D-033）。第二次跑時 `etl_job_log` 已經有該週五的 `success`，會直接印 `skipped shareholding` 離開，不會重複寫、也不會浪費請求。
4. **Mac 睡著＝沒抓到。** 週末如果筆電闔上、或 Docker Desktop 沒開，四次機會會全部 misfire。`misfire_grace_time` 是 6 小時，也就是機器在原定時間後 6 小時內醒來還補得到；超過就要手動補（見下一點），再超過就是永久缺一週。
5. **補救只有一個視窗：在官方換檔之前手動跑一次。** 週一到週五發現上週沒抓到，只要官方還沒被下一個週五的檔覆蓋，手動跑仍然抓得到那一週：

   ```bash
   docker compose exec etl \
     python -m twstock_etl.cli load-shareholding
   ```

   輸出會印出實際抓到的週五日期與筆數，例如 `loaded shareholding week=2026-09-18 rows=31204 skipped_unknown=3`。**如果印出的 `week=` 不是你要補的那一週，就是已經被覆蓋掉了，補不回來**，不要再試。

6. 一次正常載入約 **30,000+ 筆**（約 2,000 檔 × 15～17 個級距）。數量級明顯偏低就是來源格式變了，回頭看 `SourceFormatError`。
7. 沒有 `backfill shareholding` 這個子指令，**這是刻意的**（`docs/decisions.md` D-029）——不存在的歷史沒辦法回補，提供這個指令只會給人錯誤的安全感。

其他選項：`--file <路徑>`（讀本機 CSV，離線測試用）、`--force`（該週已載入過也強制重寫，來源事後更正時才需要）。

#### 7.3 手動載入單日籌碼

平時不需要（排程會跑）。想補某一天、或想立刻驗證來源格式時：

```bash
docker compose exec etl \
  python -m twstock_etl.cli load-chip --kind institutional --market TWSE --date 2026-09-18
```

- `--kind`：`institutional`（三大法人）、`margin`（融資融券）、`sbl`（借券賣出）、`foreign`（外資持股）。
- `--market`：`TWSE`、`TPEx`。**`sbl` 與 `foreign` 只有 `TWSE`**（上櫃留到 M3）；給 `--market TPEx` 會直接報錯，不會在 `etl_job_log` 留下沒意義的失敗紀錄。
- `--date`：預設台北時間今天。非交易日會被交易日曆擋下並印略過原因（`--no-calendar-check` 可略過檢查）。
- `--force`：該日已成功載入過也強制重抓。
- `--file`：讀本機 JSON，不發 HTTP（離線測試用）。

#### 7.4 籌碼回補怎麼跑

除了集保之外，四類籌碼都可以回補歷史。前置條件與第 6.1 節一樣（DB 已 migrate、**個股清單已載入**，否則會被 `stock` 表過濾掉整批）。

回補是 `backfill` 的第五個子指令，**每個 `--kind` × `--market` 組合要各跑一次**：

```bash
export DATABASE_URL="postgresql+psycopg://twstock:<你的密碼>@127.0.0.1:5432/twstock"

.venv/bin/python -m twstock_etl.cli backfill chip --kind institutional --market TWSE --from 2021-01-04 --to 2026-09-18
.venv/bin/python -m twstock_etl.cli backfill chip --kind institutional --market TPEx --from 2021-01-04 --to 2026-09-18
.venv/bin/python -m twstock_etl.cli backfill chip --kind margin        --market TWSE --from 2021-01-04 --to 2026-09-18
.venv/bin/python -m twstock_etl.cli backfill chip --kind margin        --market TPEx --from 2021-01-04 --to 2026-09-18
.venv/bin/python -m twstock_etl.cli backfill chip --kind sbl           --market TWSE --from 2021-01-04 --to 2026-09-18
.venv/bin/python -m twstock_etl.cli backfill chip --kind foreign       --market TWSE --from 2021-01-04 --to 2026-09-18
```

| 項目 | 說明 |
| --- | --- |
| 請求數 | 每個組合約 1,220 次（每交易日 1 次，5 年） |
| `--sleep 3` 預估 | 每個組合約 1～1.5 小時，六個組合**合計約 6～8 小時** |
| 順序 | 六條之間沒有相依，可以分幾天跑；但**都要在 `load-stocks` 之後** |
| 日期來源 | 只跑 `trading_calendar` 裡 `is_open=true` 的日期，所以要先有日曆（第 6.2 節步驟 1～4） |

行為與第 6 節的價格回補完全一致，**選項、進度輸出、斷點續傳、離開碼都一樣**：

- **隨時可以 Ctrl-C**，離開碼 `130`，再跑同一條指令就從中斷處繼續（`skip 已完成`）。
- 個別日期失敗照樣往下跑，結束時離開碼 `1`；直接重跑同一條指令即可重抓失敗的日期。
- 失敗超過 `--max-failures`（預設 10）會中止，離開碼 `2`——多半是被限流，用 `--sleep 6` 放慢重跑。
- 其他選項：`--force`（忽略斷點整段重抓）、`--dry-run`（只印計畫）、`--source-dir PATH`（離線模式，讀目錄下的 JSON）。

建議一樣用 `caffeinate` 並留 log：

```bash
caffeinate -i .venv/bin/python -m twstock_etl.cli backfill chip --kind margin --market TWSE \
  --from 2021-01-04 --to 2026-09-18 2>&1 | tee -a ~/twstock-backfill-margin-TWSE.log
```

#### 7.5 籌碼回補完成後的抽查

```bash
docker compose exec db psql -U twstock -d twstock -c \
  "SELECT 'institutional' AS 表, count(*), min(trade_date), max(trade_date) FROM institutional_daily
   UNION ALL SELECT 'margin', count(*), min(trade_date), max(trade_date) FROM margin_daily
   UNION ALL SELECT 'foreign', count(*), min(trade_date), max(trade_date) FROM foreign_holding
   UNION ALL SELECT 'shareholding', count(*), min(week_date), max(week_date) FROM shareholding_dist;"
```

**一定要做的一項人工核對（規格 §7 V-13）**：融資融券的來源數量單位是「張」，loader 一律 ×1000 存成「股」（`docs/decisions.md` D-036）。挑一天對一下：

```bash
docker compose exec db psql -U twstock -d twstock -c \
  "SELECT trade_date, margin_balance, short_balance FROM margin_daily WHERE stock_id='2330' ORDER BY trade_date DESC LIMIT 3;"
```

DB 的 `margin_balance` 應該等於券商軟體／官方網頁上「融資餘額（張）」的 **1000 倍**。**若不符，是 parser 要改，不是資料錯**，請回報並更新 fixture。借券（`sbl_balance`）與外資持股比例則不做換算。

### 8. 資料庫備份與還原

```bash
export DATABASE_URL="postgresql+psycopg://twstock:<你的密碼>@127.0.0.1:5432/twstock"
scripts/backup.sh                 # 預設輸出到 data/backup/
scripts/backup.sh ~/twstock-dumps # 也可以指定目錄
```

用 `pg_dump -Fc`（custom format），檔名 `twstock_YYYYmmdd_HHMMSS.dump`，**只保留最新 7 份**，舊的自動刪。成功時最後印 `BACKUP OK`。

還原到一個空庫：

```bash
pg_restore --clean --if-exists --no-owner -d "postgresql://twstock:<密碼>@127.0.0.1:5432/twstock" \
  data/backup/twstock_20260921_030000.dump
```

還原後抽查 `SELECT count(*) FROM daily_price;` 應與原庫相同（規格 §7 V-19）。備份腳本刻意**沒有**放進 compose（`docs/decisions.md` D-032）——備份該由你的 Mac 上的 launchd／cron 決定頻率，不該綁在容器生命週期上。

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

# M2 整合驗收（臨時 DB → migration → fixture 離線載入五類籌碼 → 斷點續傳檢查 → 起 API → 核對籌碼數值 → M1 價格回歸）
scripts/m2_verify.sh   # 成功時最後一行為 M2 VERIFY PASSED；每次執行會自己 reset 臨時叢集，可重複跑

# 「副圖與主圖十字線同步」的可執行版完成標準（M2 規格 §0）
cd web && npx vitest run src/chartSync.test.ts src/components/ChartStack.test.tsx

# Docker Compose 設定語法檢查（不會真的啟動）
docker compose -f deploy/docker-compose.yml --env-file .env.example config --quiet
```
