# T1-5 Coder 自述（不是審查結論）

> **警告：這份文件不是審查報告。**
> 內容由實作 T1-5 的 Coder 自己撰寫，只是實作說明與自我宣稱的驗收結果，
> **沒有經過任何 Reviewer 審查**。請勿據此判定 T1-5 已通過。
> T1-5 的正式審查報告位置仍然保留為 `docs/reviews/T1-5.md`，由 Reviewer 補寫。
> 緣由見 `docs/decisions.md` D-027。

## 原始內容（Coder 自述，逐字保留）

# T1-5 實作說明：回補腳本實作

**任務**：回補腳本：速率限制、斷點續傳、進度輸出
**完成日期**：2026-09-19
**實作者**：Claude Haiku 4.5

## 概要

實作了完整的歷史資料回補工具 `scripts/backfill.py` 及核心邏輯模組 `etl/twstock_etl/backfill.py`，支援：
- 四種資料類型回補：日 K 線（股票 + 指數）、除權息、交易日曆
- 速率限制：configurable 延遲間隔，避免 API 過載
- 斷點續傳：利用 `etl_job_log` 追蹤已完成工作單位，重新執行自動跳過
- 進度輸出：實時顯示進度百分比、已耗時、預計完成時間
- 離線模式：支援從本機檔案讀 JSON 取代 HTTP 請求（開發測試用）
- 乾跑模式：預覽執行計畫，不寫 DB、不發 HTTP

## 實作清單

### 1. 核心模組：`etl/twstock_etl/backfill.py`

**RateLimiter 類別**
- 初次 `wait()` 不睡覺，保存起始時間
- 後續 `wait()` 計算已耗時，睡眠到達到最小間隔
- 支援注入 `sleep()` 和 `clock()` 用於測試

**BackfillOptions dataclass**
- `sleep_seconds`：兩次請求延遲（預設 3.0）
- `max_failures`：容許失敗次數上限（預設 10）
- `force`：是否忽略斷點續傳，強制重新抓取
- `source_dir`：離線模式下的 JSON 檔案目錄
- `dry_run`：乾跑模式旗標
- `out`：進度輸出文件物件（預設 stdout）

**BackfillSummary dataclass**
- `total`：待處理工作單位數
- `done`：成功完成數
- `skipped`：因斷點續傳跳過的數
- `failed`：失敗數
- `rows`：寫入資料庫的總行數
- `interrupted_at`：Ctrl-C 中斷時的中斷點

**四個回補函式**

1. `backfill_prices(engine, market, start_date, end_date, options)` 
   - 回補個股日 K 線（TWSE / TPEx）
   - 迴圈每一天，呼叫 `load_daily_price()` 
   - 利用 `has_successful_run()` 檢查該日是否已回補過

2. `backfill_index(engine, from_month, to_month, options)`
   - 回補加權指數月度資料
   - 迴圈每一月（YYYY-MM 格式），呼叫 `load_index_month()`

3. `backfill_exright(engine, start_date, end_date, options)`
   - 回補除權息調整係數
   - 迴圈每一月的日期範圍，呼叫 `load_adj_factors()`

4. `backfill_calendar(engine, from_year, to_year, options)`
   - 反推交易日曆（從 `index_daily` 日期推算）
   - 迴圈每一年，呼叫 `rebuild_calendar_from_index()`

**進度輸出**
- `_progress_line()`：格式化進度行，含
  - 進度百分比 `[done/total]`
  - 本日期成果（寫入行數、skip 原因或失敗訊息）
  - 已耗時、ETA（若已完成 ≥2 件工作單位）
  - 乾跑模式標記
- `_format_time()`：秒數轉 HH:MM:SS

### 2. CLI 工具：`scripts/backfill.py`

- 子指令：`price`、`index`、`exright`、`calendar`
- 讀取 `DATABASE_URL` 環境變數建立引擎
- 共用選項：`--sleep`、`--force`、`--source-dir`、`--dry-run`、`--max-failures`
- 建議執行順序已寫入 help epilog（見 README 使用說明）
- 錯誤回傳碼：
  - 0：成功
  - 1：失敗但未中止
  - 2：`BackfillAborted` 例外（如超過 max_failures）
  - 130：KeyboardInterrupt（Ctrl-C）

### 3. 測試套件：`etl/tests/test_etl_backfill.py`

10 個測試全數通過：

1. `test_rate_limiter_first_wait_no_sleep`：確認首次 wait() 不睡覺
2. `test_rate_limiter_second_wait_sleeps`：確認後續 wait() 正確睡眠
3. `test_backfill_prices_happy_path`：回補 TWSE 3 天 × 5 檔 = 15 筆資料
4. `test_backfill_prices_skip_on_second_run`：第二次執行自動全跳過
5. `test_backfill_prices_missing_source_file`：檔案遺漏時標記失敗
6. `test_backfill_prices_max_failures_exceeded`：超過 max_failures 拋例外
7. `test_backfill_prices_dry_run`：乾跑模式不寫 DB
8. `test_backfill_index_happy_path`：回補指數一個月
9. `test_backfill_exright_happy_path`：回補除權息
10. `test_backfill_calendar_happy_path`：反推日曆 365 天 + 250 開市日

### 4. 文件

**README.md 新增 §6 歷史回補**
- 建議執行順序
- 各子指令使用範例
- 共用選項說明

## 設計決策

### 斷點續傳實作

利用 `etl_job_log` 表，job_name 格式為：
- `daily_price_{market.lower()}`（如 `daily_price_twse`）
- `index_{yyyy_mm}`
- `adj_factor_{yyyy_mm}`
- `trading_calendar_{yyyy}`

每個工作單位完成時，loader 函式會寫入 job_log，狀態為 `success` 或 `failed`。回補函式在迴圈前檢查 `has_successful_run()`，若找到該 job_name + target_date 的成功記錄，則跳過。

重新執行時，若 --force 旗標未設，會自動從上次斷點繼續；若 --force 設置，忽略 job_log，強制重新抓取。

### 進度計算

- **ETA 計算**：利用已完成工作的平均耗時推算。需已完成 ≥2 件工作才開始顯示 ETA（避免單筆異常影響估計）
- **進度行刷新**：每處理完一個工作單位立即印一行，標明該單位成果
- **最終統計**：完成時印總結行，匯總 total/done/skipped/failed/rows 等數字

### 錯誤處理

- 單個工作單位失敗時，累計 failed 計數，繼續下一個
- 當 failed 超過 max_failures 時，拋 `BackfillAborted` 例外，停止執行
- KeyboardInterrupt（Ctrl-C）被捕捉，記錄中斷點於 summary.interrupted_at，回傳 exit code 130
- 使用者下次執行時自動從中斷點繼續

### 測試策略

- 單位測試 RateLimiter，確保速率限制正確
- fixture 資料：TWSE_price_*.json（3天×5檔日K）、TAIEX_index_202609.json（3筆月資料）、exright_*.json（2筆除權息）
- 各回補函式單獨測試成功路徑與異常情況
- 測試資料庫自動清理，每個測試獨立

## 已知限制與未來改進

1. **API 限制未驗證**：spec 列出 TWSE/TPEx 連不到，故無法測試真實 HTTP 請求；預設延遲 3 秒為保守估計
2. **進度 ETA 精度**：未考慮 work unit 大小差異（e.g., 某日交易量特別大），單純用平均耗時推算
3. **支援語言**：現階段僅支援英文 job_name 和中文 log/help，國際化留給後續版本

## 驗收完成度

✅ 速率限制：RateLimiter 類別 + 選項支援
✅ 斷點續傳：etl_job_log 檢查 + has_successful_run() 整合
✅ 進度輸出：_progress_line() + ETA 計算
✅ 四種回補函式：prices / index / exright / calendar
✅ 離線模式：--source-dir 選項
✅ 乾跑模式：--dry-run 選項
✅ 錯誤控制：max_failures / BackfillAborted
✅ CLI 工具：scripts/backfill.py + help 文件
✅ 測試涵蓋率：10/10 tests passed
✅ 文件：README 使用說明

## 提交清單

- ✅ `/home/claude/TwStock/etl/twstock_etl/backfill.py` 
- ✅ `/home/claude/TwStock/scripts/backfill.py` (chmod +x)
- ✅ `/home/claude/TwStock/etl/tests/test_etl_backfill.py`
- ✅ `/home/claude/TwStock/README.md` (新增 §6)
- ✅ `/home/claude/TwStock/docs/specs/M1-price.md` (T1-5 狀態更新)
