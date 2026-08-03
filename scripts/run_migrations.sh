#!/bin/bash
# Applies any migrations/*.sql file not yet recorded in schema_migrations, in
# filename order, then records it. Safe to run repeatedly — every migration
# file in this project is written idempotently (CREATE TABLE/INDEX/COLUMN IF
# NOT EXISTS), so re-applying an already-applied file is a harmless no-op.
#
# Added after the 2026-08-02 audit found migration 006 had sat unapplied on
# the live database for weeks — the .sql file existed in this repo the whole
# time, but nothing ever recorded whether it had actually been run, so nobody
# noticed until /agent/plan started throwing 500s. Run this after every
# `git pull` / deploy instead of eyeballing which migration files look new.
set -euo pipefail
cd /root/ai-gateway
set -a
source .env
set +a

DB_URL_HOST=$(python3 /root/ai-gateway/scripts/host_db_url.py)

psql "$DB_URL_HOST" -v ON_ERROR_STOP=1 -q -c "
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"

applied_any=0
for f in migrations/*.sql; do
    name=$(basename "$f")
    already=$(psql "$DB_URL_HOST" -tA -c "SELECT 1 FROM schema_migrations WHERE filename='$name'")
    if [ "$already" = "1" ]; then
        echo "skip  $name (already applied)"
        continue
    fi
    echo "apply $name"
    psql "$DB_URL_HOST" -v ON_ERROR_STOP=1 -q -f "$f"
    psql "$DB_URL_HOST" -q -c "INSERT INTO schema_migrations (filename) VALUES ('$name')"
    applied_any=1
done

if [ "$applied_any" = "1" ]; then
    echo "Done — new migrations applied."
else
    echo "Up to date — nothing new to apply."
fi
