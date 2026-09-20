# TwStock 技術決策紀錄

格式：編號、日期、決策、理由、替代方案（與為何不選）、影響範圍。新決策往下加，推翻舊決策時新增一筆並在舊決策標註「已由 D-xxx 取代」。

編號一旦發出就不再回收或重排；若發現重複編號，保留先發出的那一筆，較晚補記的那一筆改用尚未使用過的新編號並同步更新所有引用（見 D-028）。

---

## D-001　個股清單來源：TWSE ISIN 一覽表（上市 strMode=2、上櫃 strMode=4）

- 日期：2026-09-18（M0）
- 決策：個股清單以 `https://isin.twse.com.tw/isin/C_public.jsp?strMode=2`（上市）與 `strMode=4`（上櫃）為主來源，兩者同一套 HTML 表格格式，由同一個 parser `parse_isin_html(html, market)` 處理；市場別以呼叫參數決定，不讀網頁「市場別」欄。
- 理由：
  - 同一份資料就有代號、簡稱、上市日、產業別（中文名稱）、ISIN、CFI，並以區段列出 **ETF**，可直接得到 `is_etf`。
  - 上市、上櫃格式一致，一個 parser 兩個 fixture 就能涵蓋「TWSE + TPEx」。
  - 長年穩定，社群套件（如 twstock）也使用同一來源。
- 替代方案：
  - TWSE OpenAPI `t187ap03_L` / TPEx OpenAPI `mopsfin_t187ap03_O`（公司基本資料 JSON）：只含公司、不含 ETF，產業別是代碼需另外對照；兩市場欄位命名不同，要兩個 parser。保留為之後補「公司基本資料」（統編、董事長等）的來源。
  - FinMind `TaiwanStockInfo`：方便但吃每小時配額，且每日清單屬於官方就能免費取得的資料。
- 風險：網頁為 MS950 編碼、HTML 不嚴謹（`<B>` 未關閉）。對策：`decode_isin_bytes` 先試 cp950 再退 big5hkscs；BeautifulSoup `html.parser` 容錯；解析結果為空即拋 `SourceFormatError`。

## D-002　M0 收錄範圍：上市/上櫃「股票」＋「ETF」

- 日期：2026-09-18（M0）
- 決策：只收 ISIN 一覽表中「股票」「創新板股票」「ETF」區段。TDR、特別股、權證、ETN、受益證券、興櫃（strMode=5）不收。`stock.market` 的 CHECK 仍保留 `ESB` 值，之後要收興櫃不必改 schema。
- 理由：對應 `docs/plan.md` 待決事項「是否含興櫃與 ETF」——ETF 是個人查詢常用標的且成本幾乎為零，先收；興櫃流動性低、資料源另有格式，延後。
- 替代方案：全部區段都收（權證數量上萬筆、每日大量新增下市，會污染搜尋結果）。
- 影響：`docs/plan.md` 待決事項中「是否含興櫃與 ETF」可標為「ETF 含、興櫃暫不含」（Architect 於 M0 驗收時同步更新 plan 與線上版）。

## D-003　Python 以三個本地套件組成 monorepo：twstock-db / twstock-etl / twstock-api

- 日期：2026-09-18（M0）
- 決策：`db/`（`twstock_db`：連線設定、SQLAlchemy Core 表定義、TimescaleDB 工具、Alembic migration）、`etl/`（`twstock_etl`）、`api/`（`twstock_api`）各有 `pyproject.toml`；etl 與 api 相依 `twstock-db`。開發時根目錄 `.venv` 以 `requirements-dev.txt` 安裝三者 editable；Docker 映像以 `pip install /app/db /app/<pkg>` 安裝。
- 理由：plan 要求 ETL 與 API「共用 model」；拆成獨立套件讓兩個 Docker 映像各自只帶需要的依賴，但表定義只有一份。
- 替代方案：單一 `pyproject.toml` 包全部（映像會混入 FastAPI/APScheduler 不需要的依賴）；複製表定義到兩邊（容易不同步）。

## D-004　資料存取：SQLAlchemy 2.0 Core + 同步 engine + psycopg 3；不使用 ORM、不用 async

- 日期：2026-09-18（M0）
- 決策：表以 `sqlalchemy.Table` 定義；ETL 寫入用 `postgresql.insert(...).on_conflict_do_update`；API 查詢用 `text()` 參數化 SQL；FastAPI 路由用同步 `def`（在 threadpool 執行）。
- 理由：資料流以批次 upsert 與簡單查詢為主，Core 更直接；個人單使用者系統不需要 async 的併發量；同步程式對 Coder（Haiku）與測試都比較不容易出錯。
- 替代方案：ORM（對寬表 upsert 與 hypertable 無優勢）；asyncpg + async SQLAlchemy（複雜度高、收益小）。

## D-005　Alembic migration 一律手寫，不用 autogenerate

- 日期：2026-09-18（M0）
- 決策：`env.py` 的 `target_metadata = None`；每支 migration 用 `op.create_table` 等手寫。`twstock_db/tables.py` 與 DB 結構的一致性由測試 `test_tables_py_matches_database` 把關。
- 理由：TimescaleDB（hypertable、continuous aggregate、壓縮政策）autogenerate 無法表達，且會誤判 Timescale 內部物件；手寫可控。
- 替代方案：autogenerate + 手動修正（容易漏改、產生多餘 diff）。

## D-006　TimescaleDB 採「偵測後才啟用」

- 日期：2026-09-18（M0）
- 決策：migration 0001 呼叫 `ensure_timescaledb()`：`pg_available_extensions` 有 `timescaledb` 才 `CREATE EXTENSION IF NOT EXISTS`。之後 M1 起的每日資料表用 `create_hypertable_if_available()`：`pg_extension` 已安裝才轉 hypertable，否則維持一般表並記 INFO log。continuous aggregate / 壓縮政策之後也照此模式。
- 理由：開發/CI 環境只有純 PostgreSQL 16（無 Timescale 擴充），migration 必須兩種環境都能跑；正式環境（Docker `timescale/timescaledb` 映像）自動享有分區與壓縮。
- 替代方案：強制需要 TimescaleDB（本環境無法測試 migration）；完全不用 TimescaleDB（放棄 plan 中的 continuous aggregate 與壓縮）。
- 取捨：本環境只能測到「無 Timescale」分支；「有 Timescale」分支需使用者本機 `docker compose up` 驗證（見 M0 規格 §8）。應用程式查詢不可依賴 Timescale 專屬函式（如 `time_bucket`），除非同時提供 fallback。
- 注意：若某 PostgreSQL 有擴充檔但未設定 `shared_preload_libraries`，`CREATE EXTENSION` 會失敗——這視為部署設定錯誤，不做靜默略過。

## D-007　版本鎖定策略：選成熟大版本並精確鎖定

- 日期：2026-09-18（M0）
- 決策：Python 依賴以 `==` 鎖定（FastAPI 0.115.14、SQLAlchemy 2.0.43、Alembic 1.16.5、psycopg 3.2.10、pydantic 2.11.9、APScheduler 3.11.0…），前端鎖 React 19.1、Vite 7.1、Vitest 3.2、TypeScript 5.9。不採用 registry 上更新的大版本（Vite 8、Vitest 5、TypeScript 7、APScheduler 4）。
- 理由：
  - Coder 為能力有限的模型，對較成熟版本的 API 與設定較熟悉，出錯少。
  - 新大版本（尤其 TypeScript 7 原生編譯器、APScheduler 4 全新 API）設定方式差異大、周邊套件相容性未知。
  - Architect 已於 2026-09-18 在本環境實際安裝這組版本，跑通 pytest 依賴安裝、FastAPI TestClient、vitest + Testing Library + jsdom、`tsc`、`vite build`。
- 替代方案：用最新版（風險如上）；用 `>=` 範圍（重現性差）。
- 後續：每個里程碑結束時評估一次升級，升級另開決策。

## D-008　Python 版本：映像 3.12、程式相容 3.11

- 日期：2026-09-18（M0）
- 決策：Docker 映像用 `python:3.12-slim-bookworm`（與 plan 一致）；`requires-python = ">=3.11"`，程式不得使用 3.12 專屬語法。
- 理由：開發環境只有 Python 3.11，測試必須在 3.11 跑；3.11 與 3.12 對本專案用到的語法差異極小。

## D-009　本機 DB 測試：`scripts/pg_temp.sh` 臨時 PostgreSQL 叢集

- 日期：2026-09-18（M0）
- 決策：用 `/usr/lib/postgresql/16/bin` 的 `initdb` / `pg_ctl` 在 `/tmp/twstock-pg`（port 54329）起臨時叢集，root 執行時以 `runuser -u postgres` 代跑。DB 測試讀 `TWSTOCK_TEST_DATABASE_URL`，未設定就 skip（不是 fail）；每個 pytest session 先 `alembic downgrade base` → `upgrade head`，每個測試前 TRUNCATE。里程碑驗收腳本用獨立的 `/tmp/twstock-pg-verify`（port 54330）避免干擾。
- 理由：Docker Hub 被擋無法用 testcontainers / postgres 映像；臨時叢集啟動快、測的是真正的 PostgreSQL（`ON CONFLICT`、CHECK、ILIKE 行為與正式環境相同）。
- 替代方案：SQLite（語法與 upsert 行為不同，測不準）；pytest-postgresql 套件（多一層依賴，行為與手寫腳本差不多）。
- 取捨：驗收指令明確要求「0 skipped」，避免因沒設環境變數而假通過。

## D-010　資料來源 parser 以手寫 fixture 測試，真實連線驗證留給使用者

- 日期：2026-09-18（M0）
- 決策：本開發環境連不到 TWSE / TPEx / TDCC / MOPS / FinMind。所有 parser 測試使用 `etl/tests/fixtures/` 內依官方公開格式手寫的樣本（每個 fixture 在 `README.md` 或檔頭註明來源 URL 與撰寫日期）；HTTP 行為用 `httpx.MockTransport` 測。CLI 提供 `--file` 從本機檔案載入，讓整合驗收不必連網。
- 理由：環境限制；同時 fixture 本來就是 plan 要求的「每個來源寫 parser 單元測試」。
- 風險：手寫 fixture 可能與實際回應有細節差異（欄位名、區段名稱、日期格式）。對策：parser 對未知區段忽略而非報錯、解析為空即報 `SourceFormatError`；`parse_tw_date` 同時接受民國與西元多種格式；使用者首次在本機連線執行時，以真實回應更新 fixture（M0 規格 §8 列出檢查項）。

## D-011　交易日曆：TWSE OpenAPI 休市日 + 週末規則；M0 只做當年度

- 日期：2026-09-18（M0）
- 決策：來源 `https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule`（當年度）。`build_calendar(year, holidays)`：休市條目 → 休市；週末 → 休市（note「週末」）；其餘平日 → 開市。名稱或說明含「開始交易」「最後交易」的條目是**開市日**，不能當休市；「市場無交易，僅辦理結算交割作業」視為休市。資料不含目標年份時拋錯，不產生「全平日開市」的錯誤日曆。
- 理由：官方公告最準；規則簡單可測。
- 限制：OpenAPI 只給當年度。歷史年度日曆（5 年回補需要）延到 M1，屆時以 TWSE 網站報表端點查歷年休市日，或由大盤日 K 實際有交易的日期反推。
- **年度涵蓋範圍已由 D-021 延伸**（2026-09-19，M1）：每日 job 改為刷新今年＋明年，歷史年度改由 TAIEX 指數交易日反推。`build_calendar` 本身的規則不變。
- 替代方案：寫死假日表（每年要人工維護）；`holidays` 等第三方套件（沒有台股特有的封關/開紅盤與結算交割日）。

## D-012　個股下市處理：預設不停用，需明確開啟且有筆數保護

- 日期：2026-09-18（M0）
- 決策：`upsert_stocks` 只新增/更新並把出現的個股設為 `is_active=true`；把「清單中消失」的個股設為 `is_active=false` 需呼叫端傳 `deactivate=True`（排程 job 會開，CLI 需 `--deactivate-missing`），且該市場解析筆數 < 500 時拒絕執行（在寫入前拋錯）。代號不刪除、不重用。
- 理由：來源偶發回傳不完整頁面時，若自動停用會讓大量個股從搜尋消失；上市、上櫃實際各有數百到上千檔，500 是保守下限。
- 替代方案：每次都同步停用（風險如上）；軟刪除到另一張歷程表（M0 不需要，plan 中「變更歷程表」留待有需求時做）。
- **筆數保護部分已由 D-020 取代**（2026-09-19，M1）：絕對門檻 500 筆改為相對比例 70%。本決策的其餘內容（預設不停用、需明確傳 `deactivate=True`、代號不刪除不重用）仍然有效。

## D-013　搜尋實作：ILIKE + 臺/台正規化，不用 pg_trgm 與拼音

- 日期：2026-09-18（M0）
- 決策：`GET /api/stocks?q=` 以「代號前綴 OR 名稱包含」比對，名稱比對前把「臺」換成「台」（查詢字串同樣處理），排序為完全相符 > 代號前綴 > 名稱前綴 > 名稱包含；LIKE 特殊字元以 `ESCAPE '!'` 跳脫；只回 `is_active`。
- 理由：股票約 2,000 多檔（含 ETF），全表掃描毫秒級，不需要索引；臺/台混用是台股名稱常見問題（如「臺企銀」），成本低、體感高。
- 替代方案：`pg_trgm` GIN 索引（資料量小時無明顯收益，且多一個擴充依賴）；拼音/注音搜尋（plan 列為搜尋功能之一，延後到 P1，需要額外字典）。

## D-014　部署拓樸：一次性 migrate service、同源反向代理

- 日期：2026-09-18（M0）
- 決策：
  - Compose 五個 service：`db`（`timescale/timescaledb:2.21.3-pg16`）、`migrate`（用 etl 映像跑 `alembic upgrade head` 後結束）、`api`、`etl`（APScheduler 常駐）、`web`（nginx 提供靜態檔並反向代理 `/api/` → `api:8000`）。`api`、`etl` 以 `service_completed_successfully` 等待 migrate。
  - 前端開發時用 Vite proxy `/api` → `127.0.0.1:8000`；因此全程同源、**不開 CORS**。
  - 所有對外 port 只綁 `127.0.0.1`（個人使用、不對外公開，對應 plan 的授權風險）。
- 理由：migration 只跑一次且不與 API 多副本搶鎖；同源省去 CORS 設定與安全面。
- 替代方案：API 啟動時自動 migrate（多副本會競爭、失敗時難排查）；前端直連 API + CORS。
- 環境取捨：本開發環境 Docker Hub 被擋，無法 build / up；compose 只以 `docker compose -f deploy/docker-compose.yml --env-file .env.example config` 驗證語法，映像標籤（特別是 `timescale/timescaledb:2.21.3-pg16`）需使用者首次 pull 時確認存在，若不存在改用 Docker Hub 上最新的 `2.x-pg16` 標籤並回頭更新本決策。

## D-015　U-1 真實來源格式驗證：`load-stocks` 對 TWSE／TPEx 實際跑通，parser 不用改

- 日期：2026-09-18
- 決策：本機起一個暫時的 `timescale/timescaledb:2.21.3-pg16` 容器（非 compose，單獨 `docker run`）+ Python 3.13 venv，連真實網路對 `https://isin.twse.com.tw/isin/C_public.jsp?strMode=2`（TWSE）與 `strMode=4`（TPEx）各跑一次 `python -m twstock_etl.cli load-stocks --market ...`（不帶 `--file`）。結果：TWSE 1294 筆（股票 1054＋ETF 240）、TPEx 1011 筆（股票 892＋ETF 119），皆在合理範圍（上市 1,000+、上櫃 800+），無 `SourceFormatError`，log 無「代號不符合格式」「無法拆分代號與名稱」等 warning。額外查表確認：`listed_date`／`isin_code` 無 NULL；`industry` 為 NULL 的筆數（359）恰等於 ETF 筆數（240+119），符合預期（ETF 本就無產業別）；抽查隨機列與唯一「名稱開頭是數字」的列（`6741 91APP*-KY`，真實公司名稱，非解析錯誤）皆正常。結論：`parse_isin_html` 與真實頁面格式一致，**不需要修改 parser 或補 fixture**；`etl/tests` 既有測試全數通過（無新增失敗）。
- 理由：closes M0 report U-1（真實來源格式未驗證）；本機開發環境原先連不到 TWSE，現在連得到，補齊這條驗證路徑。
- 影響範圍：無程式變動；`docs/reports/M0.md` U-1 與 README「尚未做的事」同步更新為已驗證。

## D-016　價格來源一律採「可帶日期的報表端點」，每日增量＝單日回補

- 日期：2026-09-19（M1）
- 決策：`daily_price` 的來源固定為兩個可指定日期的報表端點——上市 `https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=YYYYMMDD&type=ALLBUT0999&response=json`、上櫃 `https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=YYYY/MM/DD&type=EW&response=json`。每日盤後 job 就是「回補今天這一個日期」，與歷史回補走完全相同的程式路徑。上櫃端點另備舊版 `.../daily_close_quotes/stk_quote_result.php?l=zh-tw&d=RRR/MM/DD&o=json`，新版解析失敗時自動退回。
- 理由：
  - TWSE OpenAPI 的 `STOCK_DAY_ALL` 不含日期欄位，也無法查歷史，用它會讓「每日」與「回補」變成兩套 parser、兩組 fixture、兩種錯誤模式。
  - 每日只打 2 次請求，報表端點的頻率限制不構成問題；而回補路徑天天被執行，格式一有變動當天就會被 `etl_job_log` 抓到，不必等到下次回補。
  - 兩個端點回應都是 `{"stat","tables":[{"fields","data"}]}` 信封，可共用 `sources/report.py` 的 `extract_table`。
- 替代方案：OpenAPI 做每日、報表端點做回補（兩套程式，如上）；FinMind `TaiwanStockPrice`（吃每小時配額，5 年全市場回補會卡在 402）。
- 風險：上櫃端點是本專案目前最不確定的介面（TPEx 2024 年改版後網址與欄位名都換過）。對策＝舊版備援 + `extract_table` 以**欄位名**而非位置定位 + `--file` 可離線重跑。真實格式驗證見 `docs/specs/M1-price.md` §7 的 V-3。

## D-017　`daily_price` 不設外鍵，改由 loader 以 `stock` 表過濾；無成交列不寫入

- 日期：2026-09-19（M1）
- 決策：`daily_price`、`adj_factor` 不建 `REFERENCES stock(stock_id)` 外鍵。loader 寫入前先讀 `stock` 全部代號，不在表內的直接丟掉並回報 `skipped_unknown`。另外「成交股數為 0 且收盤價為空或 0」的列在 parser 階段就跳過，不寫入資料庫。
- 理由：
  - `MI_INDEX?type=ALLBUT0999` 會回傳受益證券、ETN、特別股、TDR 等我們在 D-002 明確不收的證券；有外鍵會讓整批 INSERT 失敗，沒有外鍵但不過濾則會污染資料表。
  - hypertable 上的外鍵在 TimescaleDB 有額外限制與效能成本，個人系統不值得。
  - 無成交日寫一列全 NULL 的 K 棒，會讓前端與均線計算多一層特例；不寫入則 K 線自然跳過那天，與券商軟體行為一致。
- 替代方案：加外鍵（整批失敗、hypertable 限制）；全部寫入不過濾（搜尋與排行會出現權證與 ETN）。
- 影響：`skipped_unknown` 是重要訊號——如果某天它突然變很大，代表 `stock` 清單沒更新或來源格式變了，`etl_job_log` 與 ETL 狀態頁都看得到。

## D-018　還原股價在 API 層即時計算，不存還原欄位

- 日期：2026-09-19（M1）
- 決策：`daily_price` 只存未還原的原始價。還原係數 `factor = 除權息參考價 ÷ 除權息前收盤價`（8 位小數）存在 `adj_factor(stock_id, ex_date)`。API `GET /api/stocks/{id}/prices?adj=true` 時，對每根 K 棒乘上「所有 `ex_date > trade_date` 的 factor 之乘積」（前復權：最新價格維持真實值，歷史價格往下調）。除權息**當天**那根不調整。成交股數、成交金額、成交筆數一律不調整。
- 理由：
  - 除權息資料常有事後更正；存還原價的話每更正一次就要重算整段歷史，存原始價則只要改一列 `adj_factor`。
  - 一檔 5 年最多數十筆 factor，2,000 根 K 棒的乘法在 API 層是微秒等級，不需要預算。
  - 「原始價」與「還原價」都能提供，使用者可以切換比對。
- 替代方案：ETL 階段算好 `adj_close` 存欄位（更正成本高、切換不了原始價）；直接抓 FinMind 的還原股價（吃配額，且無法解釋差異來源）。
- 取捨：M1 只有上市（TWSE `TWT49U`）的除權息，上櫃個股的還原 K 線在 M1 等同原始 K 線，M2 補上櫃來源。`cash_dividend` / `stock_dividend` 欄位在 M1 一律 NULL，等 M3 的股利資料。

## D-019　hypertable 建立改為「先試 by_range 新簽名，失敗退回舊簽名」，並補 mock 測試

- 日期：2026-09-19（M1）
- 決策：`create_hypertable_if_available()` 改成先執行 TimescaleDB 2.13+ 的 `create_hypertable(rel, by_range(col, interval), …)`，在 SAVEPOINT（`conn.begin_nested()`）內執行；拋 `DBAPIError` 就記 warning 並改用 2.13 之前的 `create_hypertable(rel, col, chunk_time_interval => …)`。測試以 `MagicMock` 的 Connection 驗證兩條路徑各自送出的 SQL 與參數，另加一個「有 TimescaleDB 才跑、否則 skip」的實跑測試查 `timescaledb_information.hypertables`。
- 理由：回應 M0 的 U-2。Compose 用的是 `timescale/timescaledb:2.21.3-pg16`，舊簽名在 2.13 起已標記 deprecated，未來大版本可能移除；而本開發環境沒有擴充、永遠測不到這段，所以至少要用 mock 把「送出的 SQL 長什麼樣」釘住。
- 替代方案：只寫新簽名（使用者若用舊映像會整個 migration 失敗）；只寫舊簽名（未來會壞，且 M0 已記為未解問題）；用 `SELECT extversion FROM pg_extension` 判斷版本後分支（要解析版本字串，比 try/except 脆弱）。
- 取捨：**「有 TimescaleDB 的環境」在本開發環境仍未實跑過**，只驗證了 SQL 文字與參數。實跑列在 `docs/specs/M1-price.md` §7 的 V-1，由使用者在 Mac 上 `docker compose up` 後確認。

## D-020　個股停用保護改為相對比例門檻（取代 D-012 的絕對 500 筆）

- 日期：2026-09-19（M1）
- 決策：`refresh_stock_list(..., deactivate=True)` 在同一個交易內先查該市場目前 `is_active=true` 的筆數 `previous`：
  - `previous > 0` 且本次解析筆數 `< previous × 0.7` → 拋 `SourceFormatError` 並中止（不寫入、不停用）。
  - `previous == 0`（初次建庫）且本次 `< 50` 筆 → 同樣拋錯。
  - `deactivate=False` 時完全不檢查（CLI 預設、fixture 載入不受影響）。
  兩個門檻是模組常數 `DEACTIVATE_MIN_RATIO`、`DEACTIVATE_MIN_ABSOLUTE`，測試可 monkeypatch。
- 理由：回應 M0 的 U-3。絕對門檻 500 對上櫃（約 800 檔）形同虛設——來源回 600 筆仍會通過，然後靜靜停用 200 檔。相對比例會跟著市場規模自動調整，而且「比昨天少三成」本來就是該人工確認的訊號。
- 替代方案：提高絕對門檻（每次市場擴張都要改程式）；不擋、只警告（M0 已判定風險太高）；改成標記到歷程表而不改 `is_active`（要新表，留給有需求時）。
- 影響：D-012 的「筆數保護」部分**已由本決策取代**；D-012 的其餘內容（預設不停用、代號不刪除不重用）仍然有效。失敗會寫進 `etl_job_log`（status=`failed`），ETL 狀態頁看得到。

## D-021　交易日曆：每天刷新今年＋明年；歷史年度由 TAIEX 指數反推

- 日期：2026-09-19（M1）
- 決策：
  - 每日 07:30 的 job 改為 `refresh_calendar_with_next_year(engine, 今年)`：同一份 payload 建今年與明年；明年資料官方尚未公布（`build_calendar` 拋 `SourceFormatError`）時記 INFO 略過，不算失敗。
  - 歷史年度不再去找官方歷年休市日，改用 `rebuild_calendar_from_index(engine, year)`：`index_daily` 裡該年 TAIEX 有資料的日期即開市日，其餘為休市（note「未開市（由指數回補推得）」）。少於 200 天就拒絕執行。預設 `ON CONFLICT DO NOTHING`，不覆蓋官方來源寫入的 note。
  - 因此回補順序固定為：先 `backfill.py index`，再 `backfill.py calendar`，最後 `backfill.py price`。
- 理由：回應 M0 的 U-5。TWSE OpenAPI 只給當年度，跨年會出現「1 月的排程還在用去年日曆」的空窗；而歷史年度的休市日官方沒有現成 JSON，硬爬公告頁風險高。加權指數的歷史資料本來就要抓（`index_daily` 是 M1 交付項目），用它反推是零額外請求、零額外來源的做法，而且定義上完全正確——大盤有報價的日子就是有交易的日子。
- 替代方案：爬 TWSE 歷年休市公告頁（又一個易變的 HTML 來源）；寫死假日表（每年人工維護）；由各股日 K 反推（要先有日 K，但日 K 回補又需要日曆，循環相依）。
- 取捨：反推出來的歷史日曆沒有休市原因（只有「未開市（由指數回補推得）」），而且若指數回補不完整會產生錯誤的休市日——所以設了 200 天下限，並把 note 標示清楚，之後要修正可以用 `--overwrite` 重建。

## D-022　ETL 重試機制＝「同一天排三次 + etl_job_log 去重」，不用退避重試迴圈

- 日期：2026-09-19（M1）
- 決策：每日價格 job 的 APScheduler trigger 設為 `CronTrigger(hour="15,17,19", minute=…)`；job 一開始先查 `has_successful_run(job_name, target_date)`，已成功或已跳過就記一筆 `skipped` 直接返回。`daily_price_twse` 這類 job_name **每日排程與歷史回補共用**，斷點續傳才有效。
- 理由：plan 要求「失敗自動重試 3 次」。用排程重跑而不是在 job 內迴圈重試，有三個好處：(1) 間隔以小時計，真正避得開來源暫時性故障與盤後資料延遲公布；(2) 每次嘗試都是獨立的 `etl_job_log` 列，ETL 狀態頁看得到重試了幾次；(3) 容器重啟不會丟失重試狀態。`http.get_with_retry` 的短期退避重試（處理連線抖動）仍保留，兩者互補。
- 替代方案：job 內 `for attempt in range(3): sleep(backoff)`（重試間隔太短、佔住 worker、log 不透明）；APScheduler 的 job store 持久化 + 失敗重排（多一層狀態，且我們已經有 `etl_job_log`）。
- 影響：`etl_job_log` 同一個 `(job_name, target_date)` 會有多列，查詢一律用「存在任一 success/skipped」而不是「最後一列是 success」。

## D-023　前端 K 線採 Lightweight Charts 4.2.3（v4 API），jsdom 測試以 vi.mock 取代真實繪圖

- 日期：2026-09-19（M1）
- 決策：`web/package.json` 鎖 `"lightweight-charts": "4.2.3"`，使用 v4 的 `chart.addCandlestickSeries()` / `addLineSeries()` / `addHistogramSeries()`。不採用 registry 上更新的 5.2.1（`chart.addSeries(CandlestickSeries, …)` 是全新 API）。所有會建立圖表的元件測試一律 `vi.mock('lightweight-charts')`，並在 `setupTests.ts` 補 `ResizeObserver` polyfill。
- 理由：
  - 沿用 D-007 的版本策略：Coder 是能力有限的模型，v4 的 `addXxxSeries` 寫法在文件與範例中流通最廣，v5 的 series 建構子寫法容易寫錯且錯誤訊息不直觀。
  - Architect 已於本環境 `npm i lightweight-charts@4.2.3` 實測可安裝，並確認 `dist/typings.d.ts` 含三個 `addXxxSeries` 簽名。
  - jsdom 沒有 canvas 尺寸，真的建立圖表會拋錯或畫出空白，測試價值為零；把圖表 mock 掉，測的是「資料有沒有正確流進 `setData`」與頁面互動，那才是會壞的地方。
- 替代方案：ECharts（體積大、K 線互動不如專用套件，plan 也只把它留給籌碼／財報圖）；v5（如上）；在測試裡裝 `canvas` 套件（原生編譯依賴，CI 很脆）。
- 後續：均線在前端計算（`web/src/ma.ts`），與 plan「技術指標不存 DB」一致。

## D-024　M1 範圍邊界：指數只收 TAIEX、除權息只收上市、ETL 狀態頁唯讀

- 日期：2026-09-19（M1）
- 決策：M1 的 `index_daily` 只寫入 `index_id = 'TAIEX'`（來源 `MI_5MINS_HIST`，一次一個月）；`adj_factor` 只收上市（TWSE `TWT49U`）；`/admin/etl` 是唯讀狀態頁，沒有手動重跑按鈕；不做週 K／月 K、不做技術指標、不做十字線數值面板。
- 理由：M1 的完成標準是「任一個股看得到正確還原 K 線，且排程每天自動更新」。櫃買指數與上櫃除權息各自需要再賭一個格式未知的端點，而它們對這個完成標準都不是必要條件；把它們留到 M2，可以和籌碼資料一起用同一批真實回應驗證。手動重跑需要寫入型 API 與權限考量（即使只在內網），M1 先不開。
- 替代方案：M1 一次做滿（任務數與未驗證端點數同時翻倍，違反「每階段結束都是可用系統」的節奏）。
- 影響：schema 已保留擴充空間——`index_daily` 主鍵含 `index_id`，`adj_factor` 有 `source` 欄位，兩者加來源都不必改結構。上櫃個股在 M1 勾選「還原價」時看到的就是原始 K 線，前端不必特別處理。

> 註：原本這個位置還有第二筆同樣編號為 `D-024` 的決策（ETL job 函式一律回傳結果物件），
> 編號與上面這筆重複，2026-09-21 里程碑驗收時改編為 **D-028**，內容不變，移到文件最後。

## D-025　每個會寫資料庫的 ETL job 函式都要包 `job_run`；`etl_job_log` 不得出現「正常路徑被記成 failed」

- 日期：2026-09-19（M1，T1-4 第 3 輪審查後補記）
- 決策：`refresh_stock_list`（`stock_list_twse` / `stock_list_tpex`）、`refresh_trading_calendar`（`trading_calendar`）、`rebuild_calendar_from_index`（`calendar_from_index`）比照三個價格 job 各包一層 `job_run`，簽名與回傳值不變。這些 job 不做 `has_successful_run` 去重、也不會 skip。「官方尚未公布明年度日曆」這種預期內的情況，必須在**進入 `job_run` 之前**判斷掉，只記 INFO，不可以留下 `status='failed'` 的列；`refresh_calendar_with_next_year` 因此改成「下載／解析一次 → 每年各 `build_calendar` → 私有 `_write_calendar_year` 寫入並記錄」。
- 理由：`etl_job_log` 是 ETL 狀態頁（規格 §5.4／§5.5）唯一的資料來源，也是 D-022 去重與 T1-5 斷點續傳的依據。規格 §4 的 job 名稱表從 T1-3 起就列了 `stock_list_*` 與 `trading_calendar`，但實作三輪都沒補上，等於每天真的在跑的兩個 job 在狀態頁上完全空白。同時，「近 7 天失敗次數」這個欄位只有在「失敗」真的代表異常時才有意義——把可預期的略過或尚未公布記成 failed，會讓這個欄位永遠是雜訊，和 D-028 要解決的是同一類問題（正常路徑污染錯誤訊號）。
- 替代方案：只有價格 job 記錄（狀態頁看不到個股清單與日曆，使用者最想確認的「今天清單有沒有更新」反而查不到）；由 `scheduler.py` 的 wrapper 負責記錄（CLI 手動執行就不會留紀錄，且回補腳本也要各記一次，實作會重複三份）。
- 影響：`etl_job_log` 列數增加（每天約 4 列）；T1-5 `backfill_calendar` 直接呼叫 `rebuild_calendar_from_index` 即可，不要再包一層 `job_run`；T1-6 `/api/etl/summary` 會多出三個 `job_name` 的列。

## D-026　時間相依的分支一律用可注入的 `now` 參數，不在分支裡直接呼叫 `datetime.now()`

- 日期：2026-09-19（M1，T1-4 第 3 輪審查後補記）
- 決策：任何以「現在」決定行為的分支（目前只有 `load_index_month` 的「當月一律視為未完成，不 skip」），函式要開一個關鍵字參數 `now: datetime | None = None`，內部一律 `ref = now or datetime.now(TAIPEI)`。測試必須注入固定時間覆蓋兩側分支，不得依賴跑測試當下的系統日期。CLI 與排程器不暴露這個參數。
- 理由：T1-4 第 3 輪的測試 `test_load_index_month_skip_when_done` 用的年月是 `2026-09`，剛好是跑測試當下的當月，於是「已完成就 skip」這條路徑永遠走不到——測試名稱與實際涵蓋範圍不符，第 2 輪的 `UnboundLocalError` 才會躲過整輪測試，最後靠 Reviewer 手動塞紀錄才重現。同一份測試在 2026-10 之後又會改走另一條路徑，屬於會自己變色的測試。fixture 的日期是固定的（2026-09），系統時鐘卻會前進，兩者遲早分家。
- 替代方案：測試 `monkeypatch` 掉模組層的 `datetime`（打到整個模組、容易誤傷其他用途，且錯誤訊息難懂）；用 `freezegun` 之類的套件（為一個分支多一個相依）；改用相對於 fixture 的日期常數（沒解決「當月」語意本身就依賴現在）。
- 影響：只影響 `load_index_month` 與其測試；日後 M2 若有「盤中／盤後」判斷，沿用同一個慣例。

## D-027　流程事故：Reviewer 誤判中止、Coder 自行 commit；往後 Coder 不得 commit、審查報告一律由 Reviewer 寫

- 日期：2026-09-19（M1，T1-4c～T1-6 流程事故後補記）
- 背景（事故經過）：
  1. Reviewer 把主對話裡**使用者詢問進度**的訊息當成中止指令，於是 T1-4c、T1-4d、T1-5、T1-6 **都沒有真的被審查**，卻留下 `0fe1ca4`、`21bc9c9` 兩個「未通過審查，標記 BLOCKED」的誤標 commit。
  2. `99bf0f8` commit 標題寫 `wip(T1-4d)`，但 diff 內容其實是 **T1-4c** 的程式（`etl/twstock_etl/scheduler.py` 的 `_log_job_outcome` + `etl/tests/test_etl_scheduler.py`）——未經審查就進了 `main`，而狀態表上 T1-4c 仍寫 TODO、T1-4d 被標成 BLOCKED，兩邊都與事實不符。
  3. `9f20b9c` 是 **Coder 自己 commit** 的 T1-5 回補腳本（違反流程），而且順手寫了 `docs/reviews/T1-5.md`——那份文件其實是**實作自述**（署名「實作者」、含「提交清單」），不是審查結論，卻占住了審查報告的檔名，會讓後續任何人誤以為 T1-5 已通過審查。
  4. 實際上 T1-4d（`refresh_stock_list`／`refresh_trading_calendar`／`rebuild_calendar_from_index` 補 `etl_job_log`、新增 `etl/tests/test_etl_job_records.py`）與 T1-6（API）**完全沒做**。
- 決策：
  1. **Coder 不得執行 `git commit`／`git add`**（也不得 `git push`、`git mv`、改 git 狀態）。Coder 只負責改檔案並回報；進版由 Architect 在審查通過後統一 commit。
  2. **`docs/reviews/<任務>.md` 一律由 Reviewer 撰寫**，是審查結論的唯一載體。Coder 若要寫實作說明，檔名必須是 `docs/reviews/<任務>-coder-notes.md`，且檔頭要明寫「這是 Coder 自述，不是審查結論」。本次已把 Coder 寫的 `docs/reviews/T1-5.md` 改名為 `docs/reviews/T1-5-coder-notes.md`，把審查報告的位置空出來。
  3. **狀態語意固定四種**：`TODO`（沒做）、`IN_REVIEW`（程式已在 `main`／已回報，等待審查）、`DONE`（審查通過，且 `docs/reviews/<任務>.md` 存在）、`BLOCKED`（**只有** Reviewer 實際出具 REQUEST_CHANGES 報告後才能標）。沒有審查報告就不准標 BLOCKED。
  4. **commit 標題的任務編號必須與 diff 內容相符**；Architect commit 前要用 `git diff --stat` 對一次任務編號與檔案清單。
  5. **主對話裡使用者的訊息（尤其是詢問進度）不是中止指令**。任一角色收到轉述的背景資訊時，一律把手上任務做完再回報；要中止只有 orchestrator 明確指派「中止」才算。
  6. 狀態表的真實狀態**以 git 與檔案內容為準**，不以前一輪的標記為準；發現不符時由 Architect 重建（本次已重建 `docs/specs/M1-price.md` 狀態表）。
- 理由：這次事故的三個缺陷（審查被跳過、commit 標題與內容不符、實作自述冒充審查報告）都會讓「狀態表」這個唯一的進度真相來源失真，而後續任務的相依判斷完全靠它——T1-5 的相依條件正是「T1-4a～T1-4d 全數 DONE」，在 T1-4c 未審、T1-4d 未做的情況下 T1-5 的程式就已經進了 `main`。把 commit 權收斂到 Architect、把審查報告的寫作權收斂到 Reviewer，是讓「檔案存在」這件事重新等於「有人真的看過」的最小改動。
- 替代方案：允許 Coder commit 但要求 commit 訊息自我標註「未審查」（同樣依賴自律，且 `main` 上仍會有未審程式）；用 git hook 擋 Coder 的 commit（本環境沒有可靠的角色識別，擋不住）；把審查報告改放別的目錄（換位置不解決「誰寫的」這個根本問題）。
- 影響：`main` 上目前有兩份未審程式（T1-4c 的 `scheduler.py`、T1-5 的 `backfill.py` + `scripts/backfill.py`），已在狀態表標為 `IN_REVIEW`，下一輪先補審再往下做；不做 revert，避免重寫已在 `main` 的歷史。往後每個任務的收斂順序固定為：Coder 改檔 → Reviewer 寫 `docs/reviews/<任務>.md` → Architect 改狀態表並 commit。

## D-028　ETL job 函式一律回傳結果物件；`JobSkipped` 不跨函式邊界傳播

- 日期：2026-09-19（M1，T1-4 第 3 輪審查後補記；原誤編為第二筆 `D-024`，2026-09-21 里程碑驗收時改編為 D-028）
- 決策：`jobs.py` 中每個 job 函式都回傳自己的 `@dataclass(frozen=True)`，欄位一律包含 `rows: int` 與 `skip_reason: str | None`（`PriceJobResult`、`IndexJobResult`、`AdjFactorJobResult`），不准回傳裸 `int`。`loaders/job_log.py` 的 `job_run` 維持 T1-3 定案的契約——`JobSkipped` 由 `job_run` 攔下記成 `status='skipped'`、**不往外拋**；job 函式把 `run.note` 原樣放進 `skip_reason`，呼叫端（CLI、`scheduler.py`、T1-5 回補）一律看回傳值，**全專案不准出現 `except JobSkipped`**。job 函式結尾只能有一個 `return`，所有回傳值用到的區域變數在進 `with job_run(...)` 之前就給好預設值。
- 理由：T1-4 連續三輪 REQUEST_CHANGES 的 Blocker 全部源自這個契約沒被寫清楚：(1) 第 1 輪為了讓 skip 傳到 CLI 而改掉 `job_log.py`，讓排程器把每天正常的「已完成，略過」用 `logger.exception` 記成 ERROR；(2) 第 2 輪只修了三個 job 中的一個，另外兩個在 skip 後回傳未賦值的區域變數而拋 `UnboundLocalError`，CLI 還留下 `except JobSkipped` 死碼造成 `NameError`；(3) 第 3 輪回傳型別從 `int` 改成 dataclass，`scheduler.py` 兩個呼叫端沒跟著改，`logger.info("… %d 筆", result)` 在 `logging` 內部拋 `TypeError`。「略過」是每日排程的正常路徑（見 D-022），用例外表達它，就等於讓正常路徑不斷踩到呼叫端的錯誤處理；用回傳值表達，型別檢查與測試都看得見。單一 `return` + 事先初始化則讓 `UnboundLocalError` 這一類缺陷結構上不可能發生。
- 替代方案：讓 `JobSkipped` 往外拋，呼叫端各自 `except JobSkipped`（每多一個呼叫端就多一個會漏寫的地方，第 1 輪已經實證失敗）；回傳 `int | None`，`None` 代表 skip（丟失 skip 原因，CLI 印不出 `reason=`）；改用 `typing.Protocol` 或共用基底 dataclass（對能力有限的 Coder 而言抽象成本高於收益，三個 dataclass 各自扁平就夠）。
- 影響：T1-5 `backfill.py` 的斷點續傳直接讀 `result.skip_reason` 判斷是否計入 `skipped`，不必包 `try/except`；T1-6 不直接呼叫 job 函式，不受影響。規格 `docs/specs/M1-price.md` §T1-4 已同步改寫（§3 共同契約、§4 skip 輸出格式、§5 `_log_job_outcome`）。
