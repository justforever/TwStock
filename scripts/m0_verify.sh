#!/usr/bin/env bash
# M0 整合驗收腳本：臨時 PostgreSQL + fixture 載入 + API 驗證

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export TWSTOCK_PGDATA=/tmp/twstock-pg-verify
export TWSTOCK_PGPORT=54330
UVICORN_PID=""

# 清理函式
cleanup() {
    if [ -n "$UVICORN_PID" ] && kill -0 "$UVICORN_PID" 2>/dev/null; then
        kill "$UVICORN_PID" || true
        sleep 1
    fi
    "$ROOT/scripts/pg_temp.sh" stop >/dev/null 2>&1 || true
}
trap cleanup EXIT

# 1. 啟動臨時 PostgreSQL
DATABASE_URL="$("$ROOT/scripts/pg_temp.sh" reset)"
export DATABASE_URL

# 2. 執行 migration
echo "== migrate"
"$ROOT/.venv/bin/alembic" -c "$ROOT/db/alembic.ini" upgrade head

# 3. 載入 fixture
echo "== load fixtures"
"$ROOT/.venv/bin/python" -m twstock_etl.cli load-stocks --market TWSE --file "$ROOT/etl/tests/fixtures/isin_twse_strmode2.html"
"$ROOT/.venv/bin/python" -m twstock_etl.cli load-stocks --market TPEx --file "$ROOT/etl/tests/fixtures/isin_tpex_strmode4.html"
"$ROOT/.venv/bin/python" -m twstock_etl.cli load-calendar --year 2026 --file "$ROOT/etl/tests/fixtures/twse_holiday_schedule_2026.json"

# 4. 啟動 API
echo "== start api"
"$ROOT/.venv/bin/uvicorn" twstock_api.main:app --host 127.0.0.1 --port 18000 >"/tmp/twstock-m0-api.log" 2>&1 &
UVICORN_PID=$!

# 等待 API 啟動
for i in {1..40}; do
    if curl -sf http://127.0.0.1:18000/api/health >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
    if [ $i -eq 40 ]; then
        echo "API 啟動逾時"
        cat "/tmp/twstock-m0-api.log" >&2
        exit 1
    fi
done

# 5. 驗證搜尋
echo "== verify search"
"$ROOT/.venv/bin/python" "$ROOT/scripts/verify_search_all.py" \
    --twse-file "$ROOT/etl/tests/fixtures/isin_twse_strmode2.html" \
    --tpex-file "$ROOT/etl/tests/fixtures/isin_tpex_strmode4.html"

# 6. 成功輸出
echo "M0 VERIFY PASSED"
