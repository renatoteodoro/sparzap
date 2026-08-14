#!/usr/bin/env bash
# Dump periódico do PostgreSQL compartilhado, com retenção (Sprint 19, 19.3.2).
# Roda no HOST da VPS (não dentro de um container do Sparzap), via cron:
#   0 4 * * * /caminho/para/sparzap/deploy/backup-db.sh >> /var/log/sparzap-backup.log 2>&1
set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-postgres}"      # nome do container do Postgres compartilhado
DB_NAME="${DB_NAME:-sparzap}"
DB_USER="${DB_USER:-sparzap}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/sparzap}"
RETENCAO_DIAS="${RETENCAO_DIAS:-14}"

mkdir -p "$BACKUP_DIR"
ARQUIVO="$BACKUP_DIR/sparzap-$(date +%Y%m%d-%H%M%S).sql.gz"

echo "==> gerando dump de $DB_NAME em $ARQUIVO"
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$ARQUIVO"

echo "==> removendo backups com mais de $RETENCAO_DIAS dias"
find "$BACKUP_DIR" -name 'sparzap-*.sql.gz' -mtime "+$RETENCAO_DIAS" -delete

echo "==> ok: $(ls -lh "$ARQUIVO")"
