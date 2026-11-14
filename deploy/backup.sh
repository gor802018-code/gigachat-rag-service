#!/usr/bin/env bash
# Ежедневный бэкап PostgreSQL.
#
# Запуск вручную: ./deploy/backup.sh
# По cron (каждый день в 3:15):
#   15 3 * * * cd /opt/llm-rag && ./deploy/backup.sh >> /var/log/rag-backup.log 2>&1

set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
BACKUP_DIR="${BACKUP_DIR:-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Нет $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y-%m-%d_%H%M)"
FILE="${BACKUP_DIR}/rag_${STAMP}.sql.gz"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists \
  | gzip -9 > "$FILE"

echo "Бэкап: $FILE ($(du -h "$FILE" | cut -f1))"

find "$BACKUP_DIR" -name 'rag_*.sql.gz' -type f -mtime "+${KEEP_DAYS}" -print -delete
