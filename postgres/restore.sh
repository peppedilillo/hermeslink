#!/bin/bash
set -e

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 /path/to/backup/file.sql.gz"
    exit 1
fi

source /home/dilillo/hermeslink/.postgres.env

BACKUP_FILE=$1
CONTAINER_NAME=$(docker-compose -f /home/dilillo/hermeslink/compose.prod.yml ps -q postgres)

echo "Restoring backup from $BACKUP_FILE..."
gunzip -c "$BACKUP_FILE" | docker exec -i $CONTAINER_NAME psql -U $POSTGRES_USER -d $POSTGRES_DB

echo "Restore completed"