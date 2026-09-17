#!/usr/bin/env bash
# 本機測試用臨時 PostgreSQL 16 叢集（無 TimescaleDB）。用法：scripts/pg_temp.sh start|stop|reset
set -euo pipefail
PGBIN=/usr/lib/postgresql/16/bin
PGDATA=${TWSTOCK_PGDATA:-/tmp/twstock-pg}
PORT=${TWSTOCK_PGPORT:-54329}
as_pg() { if [ "$(id -u)" = "0" ]; then runuser -u postgres -- "$@"; else "$@"; fi; }
psql_pg() { as_pg $PGBIN/psql -h 127.0.0.1 -p "$PORT" -U postgres -v ON_ERROR_STOP=1 "$@"; }
case "${1:-}" in
start)
  if [ ! -f "$PGDATA/PG_VERSION" ]; then
    mkdir -p "$PGDATA"
    if [ "$(id -u)" = "0" ]; then chown postgres:postgres "$PGDATA"; fi
    as_pg $PGBIN/initdb -D "$PGDATA" -U postgres --auth=trust -E UTF8 --locale=C.UTF-8 >/dev/null
  fi
  as_pg $PGBIN/pg_ctl -D "$PGDATA" status >/dev/null 2>&1 || \
    as_pg $PGBIN/pg_ctl -D "$PGDATA" -o "-p $PORT -k /tmp -c listen_addresses=127.0.0.1" -l "$PGDATA/server.log" -w start >/dev/null
  psql_pg -tAc "SELECT 1 FROM pg_roles WHERE rolname='twstock'" | grep -q 1 || \
    psql_pg -c "CREATE ROLE twstock LOGIN PASSWORD 'twstock'" >/dev/null
  psql_pg -tAc "SELECT 1 FROM pg_database WHERE datname='twstock_test'" | grep -q 1 || \
    psql_pg -c "CREATE DATABASE twstock_test OWNER twstock" >/dev/null
  echo "postgresql+psycopg://twstock:twstock@127.0.0.1:$PORT/twstock_test"
  ;;
stop)
  as_pg $PGBIN/pg_ctl -D "$PGDATA" -m fast -w stop >/dev/null 2>&1 || true
  echo "stopped"
  ;;
reset)
  "$0" stop >/dev/null
  rm -rf "$PGDATA"
  "$0" start
  ;;
*)
  echo "用法：$0 start|stop|reset" >&2
  exit 2
  ;;
esac
