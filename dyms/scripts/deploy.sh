#!/bin/bash
# DYMS Deployment Script
# Usage: ./deploy.sh [--build] [--migrate]

set -euo pipefail

DEPLOY_DIR="/opt/dyms"
COMPOSE_FILE="docker-compose.prod.yml"
BACKUP_DIR="/opt/dyms/backups"

echo "========================================"
echo "  DYMS Deploy — $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

cd $DEPLOY_DIR

# 1. Database backup
echo "[1/6] Backing up database..."
mkdir -p $BACKUP_DIR
docker exec dyms-db pg_dump -U dyms dyms | gzip > \
    "$BACKUP_DIR/dyms_$(date +%Y%m%d_%H%M%S).sql.gz"
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
echo "  -> Backup complete"

# 2. Pull latest code
echo "[2/6] Pulling code..."
git pull origin main
echo "  -> Code updated"

# 3. Build (optional)
if [[ "${1:-}" == "--build" ]] || [[ "${2:-}" == "--build" ]]; then
    echo "[3/6] Building Docker image..."
    docker compose -f $COMPOSE_FILE build --no-cache api
    echo "  -> Image built"
else
    echo "[3/6] Skipping build (use --build to rebuild)"
fi

# 4. Migrate (optional)
if [[ "${1:-}" == "--migrate" ]] || [[ "${2:-}" == "--migrate" ]]; then
    echo "[4/6] Running database migrations..."
    docker compose -f $COMPOSE_FILE run --rm api alembic upgrade head
    echo "  -> Migrations complete"
else
    echo "[4/6] Skipping migrations (use --migrate to run)"
fi

# 5. Restart
echo "[5/6] Restarting services..."
docker compose -f $COMPOSE_FILE up -d --remove-orphans
echo "  -> Services restarted"

# 6. Health check
echo "[6/6] Health check..."
sleep 5
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health)
if [ "$HTTP_CODE" == "200" ]; then
    echo "  -> DYMS running (HTTP $HTTP_CODE)"
else
    echo "  -> Health check FAILED (HTTP $HTTP_CODE)"
    echo "  -> Logs: docker logs dyms-api --tail 50"
    exit 1
fi

echo ""
echo "========================================"
echo "  Deploy complete!"
echo "  DYMS:  https://dyms.missgtrading.com"
echo "========================================"
