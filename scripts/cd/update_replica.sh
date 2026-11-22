#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo "Usage: $0 <service> <image> <dry-run|deploy>"
    exit 2
fi

SERVICE="$1"
IMAGE="$2"
MODE="$3"

case "$SERVICE" in
    api-replica1)
        PORT=8002
        ;;
    api-replica2)
        PORT=8003
        ;;
    *)
        echo "ERROR: unknown service: $SERVICE"
        exit 2
        ;;
esac

case "$MODE" in
    dry-run|deploy) ;;
    *)
        echo "ERROR: mode must be dry-run or deploy"
        exit 2
        ;;
esac

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infrastructure/api/docker-compose.yml"

# Load deployment identity from root-owned configuration.
CONFIG_FILE="/etc/mlops-cd/deploy.env"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: missing CD configuration: $CONFIG_FILE"
    exit 1
fi

set -a
source "$CONFIG_FILE"
set +a

: "${API_UID:?API_UID is required}"
: "${API_GID:?API_GID is required}"
: "${API_AWS_DIR:?API_AWS_DIR is required}"

if [[ ! "$API_UID" =~ ^[0-9]+$ ]] ||
   [[ ! "$API_GID" =~ ^[0-9]+$ ]] ||
   [[ "$API_AWS_DIR" != "/home/iu31101987/.aws" ]]; then
    echo "ERROR: invalid CD identity configuration"
    exit 1
fi

IMAGE_ID="$(sudo docker image inspect "$IMAGE" --format '{{.Id}}')"

OVERRIDE_FILE="$(mktemp /tmp/mlops-cd-XXXXXX.yml)"
trap 'rm -f "$OVERRIDE_FILE"' EXIT

cat > "$OVERRIDE_FILE" <<YAML
services:
  $SERVICE:
    image: "$IMAGE"
YAML

compose() {
    sudo --preserve-env=API_UID,API_GID,API_AWS_DIR \
        docker compose \
        --project-name api \
        -f "$COMPOSE_FILE" \
        -f "$OVERRIDE_FILE" \
        "$@"
}

echo "=== Проверяем конфигурацию ==="
compose config --quiet

echo "Service: $SERVICE"
echo "Image: $IMAGE"
echo "Image ID: $IMAGE_ID"
echo "Mode: $MODE"

if [[ "$MODE" == "dry-run" ]]; then
    echo "SUCCESS: dry-run; контейнер не изменён"
    exit 0
fi

echo "=== Обновляем $SERVICE ==="

compose up -d \
    --no-deps \
    --force-recreate \
    --pull never \
    --no-build \
    "$SERVICE"

echo "=== Проверяем здоровье ==="

python3 "$ROOT_DIR/scripts/cd/healthcheck.py" \
    --url "http://127.0.0.1:$PORT/health" \
    --retries 15 \
    --interval 2

echo "=== Проверяем фактический Docker Image ID ==="

case "$SERVICE" in
    api-replica1)
        CONTAINER="ecommerce-purchase-api-monitoring"
        ;;
    api-replica2)
        CONTAINER="ecommerce-purchase-api-replica2"
        ;;
esac

ACTUAL_ID="$(
    sudo docker inspect "$CONTAINER" --format '{{.Image}}'
)"

if [[ "$ACTUAL_ID" != "$IMAGE_ID" ]]; then
    echo "ERROR: unexpected image in $CONTAINER"
    echo "Expected: $IMAGE_ID"
    echo "Actual: $ACTUAL_ID"
    exit 1
fi

echo "SUCCESS: Docker Image ID verified"
echo "SUCCESS: $SERVICE updated"
