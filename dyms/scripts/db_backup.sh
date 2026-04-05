#!/bin/bash
# Daily database backup script
# Add to crontab: 0 3 * * * /opt/dyms/scripts/db_backup.sh

BACKUP_DIR="/opt/dyms/backups"
mkdir -p $BACKUP_DIR

docker exec dyms-db pg_dump -U dyms -Fc dyms > \
    "$BACKUP_DIR/dyms_full_$(date +%Y%m%d).dump"

find $BACKUP_DIR -name "*.dump" -mtime +30 -delete
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete

echo "[$(date)] DB backup completed" >> /var/log/dyms_backup.log
