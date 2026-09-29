#!/usr/bin/env sh
# Restore a backup made by backup.sh (stops the API and worker while restoring).
#   scripts/restore.sh /var/backups/lishebora/db-20261001-0130.dump /var/backups/lishebora/storage-20261001-0130.tgz
set -eu
[ $# -eq 2 ] || { echo "usage: restore.sh DB_DUMP STORAGE_TGZ"; exit 1; }
cd "$(dirname "$0")/.."
C="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env"
$C stop backend worker
$C exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < "$1"
$C run --rm -T --entrypoint sh backend -c 'rm -rf /data/storage/* && tar -C /data -xzf -' < "$2"
$C start backend worker
echo "Restore complete."
