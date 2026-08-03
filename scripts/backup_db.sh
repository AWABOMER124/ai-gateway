#!/bin/bash
# Daily backup for the ai-gateway Postgres database (awab_ai).
# Added after the 2026-08-02 audit found zero automated backups existed.
set -euo pipefail
cd /root/ai-gateway
set -a
source .env
set +a

BACKUP_DIR="/root/backups/ai-gateway"
mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d_%H%M%S)
OUT="$BACKUP_DIR/awab_ai_${TS}.sql.gz"

# DATABASE_URL uses host.docker.internal, resolvable only from inside containers.
# This script runs on the bare host, where the same published port is 127.0.0.1.
DB_URL_HOST=$(echo "$DATABASE_URL" | sed 's/host\.docker\.internal/127.0.0.1/')

pg_dump "$DB_URL_HOST" | gzip > "$OUT"

# Retention: keep 14 days of daily backups.
find "$BACKUP_DIR" -name 'awab_ai_*.sql.gz' -mtime +14 -delete

echo "$(date -Iseconds) Backup OK: $OUT ($(du -h "$OUT" | cut -f1))"
