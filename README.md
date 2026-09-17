# TwStock

個人台股查詢系統：每日盤後自動抓資料進資料庫，網頁查個股 K 線、籌碼、基本面。

- 設計計劃：[docs/plan.md](docs/plan.md)
- 專案規則與目錄說明：[CLAUDE.md](CLAUDE.md)

目前進度：M0（骨架）規格完成，實作中（見 [docs/specs/M0-skeleton.md](docs/specs/M0-skeleton.md)）。

## 快速開始

### Docker（推薦用於部署）

本機須安裝 Docker 與 Docker Compose。

```bash
# 複製範本設定並修改密碼
cp .env.example .env
# 編輯 .env，改 POSTGRES_PASSWORD

# 啟動全部 service（首次會下載映像與建置）
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build

# 開啟瀏覽器查詢：http://localhost:8080
# 首次啟動時 etl service 會立即抓取個股清單與交易日曆，約需 1～2 分鐘
```

查看 logs：`docker compose -f deploy/docker-compose.yml logs -f etl`

停止：`docker compose -f deploy/docker-compose.yml down`

### 本機開發（無 Docker）

要求：Python 3.11+、PostgreSQL 16、Node 22。

```bash
# 1. 虛擬環境與依賴
python3 -m venv .venv
source .venv/bin/activate  # 或 Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# 2. 臨時資料庫
scripts/pg_temp.sh start
export DATABASE_URL="postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test"
.venv/bin/alembic -c db/alembic.ini upgrade head

# 3. 載入範例資料（用 fixture，不連網）
.venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html
.venv/bin/python -m twstock_etl.cli load-stocks --market TPEx --file etl/tests/fixtures/isin_tpex_strmode4.html

# 4. 啟動 API（別的終端機）
.venv/bin/uvicorn twstock_api.main:app --host 127.0.0.1 --port 8000

# 5. 啟動前端開發伺服器（別的終端機）
cd web
npm install
npm run dev
# 開 http://localhost:5173
```

停止資料庫：`scripts/pg_temp.sh stop`

### 測試

```bash
# 後端測試
TWSTOCK_TEST_DATABASE_URL="postgresql+psycopg://twstock:twstock@127.0.0.1:54329/twstock_test" \
  .venv/bin/python -m pytest

# 前端測試
cd web && npm test

# 整合驗收
scripts/m0_verify.sh
```
