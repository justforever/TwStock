# TwStock 專案規則

- 所有跟 TwStock 相關的產出（程式、網頁、SQL、設定、文件、腳本）一律放在這個資料夾內，不放其他地方。
- 語言：文件與註解用繁體中文；程式識別字用英文。
- 設計計劃：`docs/plan.md`（線上版：https://claude.ai/code/artifact/81713bf5-0494-47e6-8fff-bdba43f20a9b）。架構或 schema 有變動時，兩邊一起更新。

## 目錄結構

| 路徑 | 內容 |
| --- | --- |
| `docs/` | 設計文件、決策紀錄、資料來源筆記 |
| `etl/` | Python ETL worker（抓 TWSE/TPEx/TDCC/MOPS/FinMind，APScheduler 排程） |
| `api/` | FastAPI 後端 |
| `web/` | React + Vite + TypeScript 前端（Lightweight Charts / ECharts） |
| `db/migrations/` | Alembic migration、初始化 SQL（PostgreSQL + TimescaleDB） |
| `deploy/` | Docker Compose、Helm chart、環境設定 |
| `scripts/` | 一次性工具：歷史回補、資料校驗 |
| `docs/specs/` | Architect 的里程碑規格與任務單 |
| `docs/reviews/` | Reviewer 的審查報告 |
| `.claude/agents/` | Agent 團隊定義（architect / coder / reviewer） |

## 慣例

- 股數單位一律「股」，金額 `NUMERIC`，日期為台北時間交易日。
- 每日資料表主鍵 `(stock_id, trade_date)`，寫入用 `INSERT ... ON CONFLICT DO UPDATE`。
- 機密（FinMind token、DB 密碼）放 `.env`，不進版控；範本在 `.env.example`。

## Agent 團隊

開發採 Architect → Coder → Reviewer 流程，詳見 `docs/team.md`。Coder 只做規格裡指定的任務，規格不清楚就停下來問。
