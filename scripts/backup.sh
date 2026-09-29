#!/usr/bin/env sh
# Nightly backup: database dump + uploaded files. Keep 14 days locally; copy the folder off-site as well.
#   crontab:  30 1 * * *  /opt/lishebora/scripts/backup.sh >> /var/log/lishebora-backup.log 2>&1
set -eu
cd "$(dirname "$0")/.."
STAMP=$(date +%Y%m%d-%H%M)
DEST=${BACKUP_DIR:-/var/backups/lishebora}
mkdir -p "$DEST"
C="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env"
$C exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$DEST/db-$STAMP.dump"
$C exec -T backend tar -C /data -czf - storage > "$DEST/storage-$STAMP.tgz"
find "$DEST" -type f -mtime +14 -delete
echo "Backup written: $DEST/db-$STAMP.dump and storage-$STAMP.tgz"
