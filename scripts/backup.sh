#!/usr/bin/env bash
# TwStock 資料庫備份。用法：scripts/backup.sh [備份目錄]（預設 data/backup）
# 需要環境變數 DATABASE_URL，格式 postgresql+psycopg://user:pass@host:port/dbname
set -euo pipefail

# 取得根目錄
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 檢查 DATABASE_URL
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "錯誤：未設定 DATABASE_URL" >&2
    exit 1
fi

# 把 SQLAlchemy 的 driver 後綴換掉
PG_URL="${DATABASE_URL#postgresql+psycopg://}"
PG_URL="postgresql://${PG_URL}"

# 備份目錄
OUT_DIR="${1:-$ROOT/data/backup}"
mkdir -p "$OUT_DIR"

# 檔名
NAME="twstock_$(date +%Y%m%d_%H%M%S).dump"

# 找 pg_dump
PG_DUMP=""
if command -v pg_dump &>/dev/null; then
    PG_DUMP="pg_dump"
elif [[ -f "/usr/lib/postgresql/16/bin/pg_dump" ]]; then
    PG_DUMP="/usr/lib/postgresql/16/bin/pg_dump"
else
    echo "錯誤：找不到 pg_dump" >&2
    exit 1
fi

# 執行備份
"$PG_DUMP" --format=custom --no-owner --no-privileges --file="$OUT_DIR/$NAME" "$PG_URL"

# 只保留最新 7 份
ls -1t "$OUT_DIR"/twstock_*.dump 2>/dev/null | tail -n +8 | xargs -r rm -f

# 計算檔案大小
SIZE=$(du -h "$OUT_DIR/$NAME" | cut -f1)

# 成功訊息
echo "BACKUP OK $OUT_DIR/$NAME $SIZE"
