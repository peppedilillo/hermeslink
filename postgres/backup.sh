#!/bin/bash
set -e
source /home/dilillo/hermeslink/.postgres.env

BACKUP_DIR=/home/dilillo/hermeslink-backup
RETENTION_DAYS=14
CONTAINER_NAME=$(docker compose -f /home/dilillo/hermeslink/compose.prod.yml ps -q postgres)

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p $BACKUP_DIR
echo "Creating database backup: $BACKUP_DIR/hlink_backup_$TIMESTAMP.sql.gz"
docker exec $CONTAINER_NAME pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > "$BACKUP_DIR/hlink_backup_$TIMESTAMP.sql.gz"

if [ ! -s "$BACKUP_DIR/hlink_backup_$TIMESTAMP.sql.gz" ]; then
    echo "ERROR: Backup file is empty or does not exist!"
    exit 1
fi

find $BACKUP_DIR -name "hlink_backup_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete
echo "Backup completed successfully"