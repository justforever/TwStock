# TwStock 技術決策紀錄

格式：編號、日期、決策、理由、替代方案（與為何不選）、影響範圍。新決策往下加，推翻舊決策時新增一筆並在舊決策標註「已由 D-xxx 取代」。

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
- 替代方案：寫死假日表（每年要人工維護）；`holidays` 等第三方套件（沒有台股特有的封關/開紅盤與結算交割日）。

## D-012　個股下市處理：預設不停用，需明確開啟且有筆數保護

- 日期：2026-09-18（M0）
- 決策：`upsert_stocks` 只新增/更新並把出現的個股設為 `is_active=true`；把「清單中消失」的個股設為 `is_active=false` 需呼叫端傳 `deactivate=True`（排程 job 會開，CLI 需 `--deactivate-missing`），且該市場解析筆數 < 500 時拒絕執行（在寫入前拋錯）。代號不刪除、不重用。
- 理由：來源偶發回傳不完整頁面時，若自動停用會讓大量個股從搜尋消失；上市、上櫃實際各有數百到上千檔，500 是保守下限。
- 替代方案：每次都同步停用（風險如上）；軟刪除到另一張歷程表（M0 不需要，plan 中「變更歷程表」留待有需求時做）。

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
