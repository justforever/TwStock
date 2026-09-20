#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TWSTOCK_PGDATA=/tmp/twstock-pg-m1
TWSTOCK_PGPORT=54331
API_PORT=18001

# 清理函式
cleanup() {
  echo "== cleanup"
  pkill -f "uvicorn" || true
  "$ROOT/scripts/pg_temp.sh" stop || true
}

trap cleanup EXIT

# 重設資料庫
echo "== reset database"
export DATABASE_URL=$(TWSTOCK_PGDATA=$TWSTOCK_PGDATA TWSTOCK_PGPORT=$TWSTOCK_PGPORT "$ROOT/scripts/pg_temp.sh" reset)

# 執行 migration
echo "== migrate"
cd "$ROOT"
.venv/bin/alembic -c db/alembic.ini upgrade head >/dev/null

# 載入 fixture
echo "== load fixtures"
.venv/bin/python -m twstock_etl.cli load-stocks --market TWSE --file etl/tests/fixtures/isin_twse_strmode2.html >/dev/null
.venv/bin/python -m twstock_etl.cli load-stocks --market TPEx --file etl/tests/fixtures/isin_tpex_strmode4.html >/dev/null
.venv/bin/python -m twstock_etl.cli load-calendar --year 2026 --file etl/tests/fixtures/twse_holiday_schedule_2026.json >/dev/null

# 回補指數
echo "== backfill index"
.venv/bin/python scripts/backfill.py index --from 2026-09 --to 2026-09 --source-dir etl/tests/fixtures --sleep 0 >/dev/null

# 回補日 K - TWSE
echo "== backfill price"
.venv/bin/python scripts/backfill.py price --market TWSE --from 2026-09-16 --to 2026-09-18 --source-dir etl/tests/fixtures --sleep 0 >/dev/null

# 回補日 K - TPEx
.venv/bin/python scripts/backfill.py price --market TPEx --from 2026-09-16 --to 2026-09-18 --source-dir etl/tests/fixtures --sleep 0 >/dev/null

# 回補除權除息
echo "== backfill exright"
.venv/bin/python scripts/backfill.py exright --from 2026-09-01 --to 2026-09-30 --source-dir etl/tests/fixtures --sleep 0 >/dev/null

# 驗證斷點續傳
echo "== resume check"
OUT=$(.venv/bin/python scripts/backfill.py price --market TWSE --from 2026-09-16 --to 2026-09-18 --source-dir etl/tests/fixtures --sleep 0 2>&1 || true)
SKIP_COUNT=$(echo "$OUT" | grep -c 'skip' || true)
if [ "$SKIP_COUNT" != "3" ]; then
  echo "Resume check failed: expected 3 skips, got $SKIP_COUNT"
  echo "$OUT"
  exit 1
fi

# 啟動 API
echo "== start api"
cd "$ROOT"
.venv/bin/python -m uvicorn twstock_api.main:app --host 127.0.0.1 --port $API_PORT >/dev/null 2>&1 &
API_PID=$!

# 等待 API 啟動
sleep 2
if ! kill -0 $API_PID 2>/dev/null; then
  echo "API failed to start"
  exit 1
fi

# 驗證價格
echo "== verify prices"
.venv/bin/python scripts/verify_prices.py --api-base http://127.0.0.1:$API_PORT

echo "M1 VERIFY PASSED"
