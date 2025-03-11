#!/bin/bash
set -eo pipefail
source /home/dilillo/hermeslink/.postgres.env

BACKUP_DIR=/home/dilillo/data/docker-volumes/hlink/postgres-backup
RETENTION_DAYS=14
COMPOSE_FILE=/home/dilillo/hermeslink/compose.prod.yml

# check if container exists and is running
CONTAINER_NAME=$(docker-compose -f $COMPOSE_FILE ps -q postgres)
if [ -z "$CONTAINER_NAME" ]; then
    echo "ERROR: PostgreSQL container is not defined or not created."
    exit 1
fi

# check container is actually running
if ! docker ps --format '{{.ID}}' --no-trunc | grep -q "$CONTAINER_NAME"; then
    echo "ERROR: PostgreSQL container exists but is not running."
    echo "Please start the database container with: docker-compose -f $COMPOSE_FILE up -d postgres"
    exit 1
fi

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
