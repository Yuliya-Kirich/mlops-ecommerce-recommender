#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infrastructure/api/docker-compose.yml"

REPLICA1="ecommerce-purchase-api-monitoring"
REPLICA2="ecommerce-purchase-api-replica2"

HEALTH1="http://127.0.0.1:8002/health"
HEALTH2="http://127.0.0.1:8003/health"
HEALTH_NGINX="http://127.0.0.1:8004/health"

MODE="${1:---dry-run}"

case "$MODE" in
    --dry-run)
        ;;
    *)
        echo "ERROR: пока поддерживается только --dry-run"
        exit 2
        ;;
esac

cd "$ROOT_DIR"

echo "=== CD deployment plan ==="
echo "Mode: DRY RUN"
echo "Compose: $COMPOSE_FILE"

echo "=== Проверяем текущие образы ==="

OLD_IMAGE1="$(sudo docker inspect "$REPLICA1" --format '{{.Image}}')"
OLD_IMAGE2="$(sudo docker inspect "$REPLICA2" --format '{{.Image}}')"

sudo docker image inspect "$OLD_IMAGE1" >/dev/null
sudo docker image inspect "$OLD_IMAGE2" >/dev/null

echo "Replica 1 rollback image: $OLD_IMAGE1"
echo "Replica 2 rollback image: $OLD_IMAGE2"

echo "=== Проверяем целевой Docker-образ ==="

TARGET_IMAGE="${CD_IMAGE:-cr.yandex/crp2g9e8cdlnstpbrr5n/ecommerce-purchase-api:1.1}"

TARGET_IMAGE_ID="$(
    sudo docker image inspect "$TARGET_IMAGE" --format '{{.Id}}'
)"

echo "Target image: $TARGET_IMAGE"
echo "Target Image ID: $TARGET_IMAGE_ID"

if [[ "$OLD_IMAGE1" == "$TARGET_IMAGE_ID" &&
      "$OLD_IMAGE2" == "$TARGET_IMAGE_ID" ]]; then
    echo "INFO: обе реплики уже используют целевой образ"
    echo "INFO: обновление контейнеров не требуется"
else
    echo "INFO: обнаружено отличие образов"
    echo "INFO: при настоящем CD потребуется обновление реплик"
fi

echo "=== Проверяем здоровье сервиса ==="

python3 scripts/cd/healthcheck.py --url "$HEALTH1" --retries 1
python3 scripts/cd/healthcheck.py --url "$HEALTH2" --retries 1
python3 scripts/cd/healthcheck.py --url "$HEALTH_NGINX" --retries 1

echo "=== План обновления ==="
echo "1. Сохранить предыдущие образы по Image ID"
echo "2. Обновить api-replica1"
echo "3. Проверить api-replica1 и Nginx"
echo "4. Обновить api-replica2"
echo "5. Проверить api-replica2 и Nginx"
echo "6. При ошибке восстановить предыдущие образы"

echo "SUCCESS: dry-run completed; no containers changed"
