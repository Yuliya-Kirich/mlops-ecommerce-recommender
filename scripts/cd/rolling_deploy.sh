#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE_SCRIPT="$ROOT_DIR/scripts/cd/update_replica.sh"
HEALTH_SCRIPT="$ROOT_DIR/scripts/cd/healthcheck.py"

MODE="${1:---dry-run}"
TARGET_IMAGE="${CD_IMAGE:-cr.yandex/crp2g9e8cdlnstpbrr5n/ecommerce-purchase-api:1.1}"

case "$MODE" in
    --dry-run|--deploy) ;;
    *)
        echo "ERROR: use --dry-run or --deploy"
        exit 2
        ;;
esac

if [[ "$MODE" == "--deploy" &&
      "${CD_CONFIRM_DEPLOY:-}" != "YES" ]]; then
    echo "ERROR: set CD_CONFIRM_DEPLOY=YES for real deployment"
    exit 2
fi

cd "$ROOT_DIR"

if [[ "$MODE" == "--deploy" ]]; then
    # Блокируем CD до проверки и сохранения исходных Image ID.
    exec 9>/run/mlops-cd/locks/mlops-api-cd.lock
    if ! flock -n 9; then
        echo "ERROR: another deployment is running"
        exit 1
    fi
fi

check_health() {
    python3 "$HEALTH_SCRIPT" \
        --url "$1" \
        --retries 15 \
        --interval 2
}

echo "=== Проверяем целевой образ ==="

TARGET_ID="$(
    sudo docker image inspect "$TARGET_IMAGE" --format '{{.Id}}'
)"

echo "Target image: $TARGET_IMAGE"
echo "Target Image ID: $TARGET_ID"

echo "=== Сохраняем текущие образы ==="

OLD_IMAGE1="$(
    sudo docker inspect ecommerce-purchase-api-monitoring \
        --format '{{.Image}}'
)"

OLD_IMAGE2="$(
    sudo docker inspect ecommerce-purchase-api-replica2 \
        --format '{{.Image}}'
)"

sudo docker image inspect "$OLD_IMAGE1" >/dev/null
sudo docker image inspect "$OLD_IMAGE2" >/dev/null

echo "Replica 1 rollback: $OLD_IMAGE1"
echo "Replica 2 rollback: $OLD_IMAGE2"

echo "=== Проверяем состояние API ==="

for port in 8002 8003 8004; do
    check_health "http://127.0.0.1:$port/health"
done

echo "=== Проверяем конфигурацию обновления ==="

bash "$UPDATE_SCRIPT" api-replica1 "$TARGET_IMAGE" dry-run
bash "$UPDATE_SCRIPT" api-replica2 "$TARGET_IMAGE" dry-run

if [[ "$MODE" == "--dry-run" ]]; then
    echo "SUCCESS: rolling deployment dry-run completed"
    echo "No containers were changed"
    exit 0
fi

echo "=== Начинаем rolling deployment ==="


CHANGED1=0
CHANGED2=0
DEPLOY_SUCCESS=0

rollback() {
    local original_status=$?
    local failed=0
    local actual_id

    trap - EXIT

    if [[ "$DEPLOY_SUCCESS" == 1 ]]; then
        return 0
    fi

    echo "=== ERROR: deployment failed, starting rollback ==="

    if [[ "$CHANGED2" == 1 ]]; then
        bash "$UPDATE_SCRIPT" \
            api-replica2 "$OLD_IMAGE2" deploy \
            || failed=1
    fi

    if [[ "$CHANGED1" == 1 ]]; then
        bash "$UPDATE_SCRIPT" \
            api-replica1 "$OLD_IMAGE1" deploy \
            || failed=1
    fi

    echo "=== Проверяем восстановленные Docker-образы ==="

    if ! actual_id="$(
        sudo docker inspect ecommerce-purchase-api-monitoring \
            --format '{{.Image}}'
    )" || [[ "$actual_id" != "$OLD_IMAGE1" ]]; then
        echo "ERROR: replica1 image was not restored"
        failed=1
    fi

    if ! actual_id="$(
        sudo docker inspect ecommerce-purchase-api-replica2 \
            --format '{{.Image}}'
    )" || [[ "$actual_id" != "$OLD_IMAGE2" ]]; then
        echo "ERROR: replica2 image was not restored"
        failed=1
    fi

    echo "=== Проверяем здоровье после отката ==="

    for port in 8002 8003 8004; do
        if ! check_health "http://127.0.0.1:$port/health"; then
            echo "ERROR: healthcheck failed on port $port"
            failed=1
        fi
    done

    if [[ "$failed" == 0 ]]; then
        echo "SUCCESS: rollback completed and verified"
    else
        echo "CRITICAL: rollback incomplete; manual recovery required"
    fi

    exit "$original_status"
}

trap rollback EXIT

if [[ "$OLD_IMAGE1" != "$TARGET_ID" ]]; then
    echo "=== Обновляем первую реплику ==="

    CHANGED1=1

    bash "$UPDATE_SCRIPT" \
        api-replica1 "$TARGET_IMAGE" deploy

    check_health "http://127.0.0.1:8004/health"
else
    echo "Replica 1 already uses target image"
fi

if [[ "$OLD_IMAGE2" != "$TARGET_ID" ]]; then
    echo "=== Обновляем вторую реплику ==="

    CHANGED2=1

    bash "$UPDATE_SCRIPT" \
        api-replica2 "$TARGET_IMAGE" deploy

    check_health "http://127.0.0.1:8004/health"
else
    echo "Replica 2 already uses target image"
fi

echo "=== Проверяем финальные Image ID ==="

for container in \
    ecommerce-purchase-api-monitoring \
    ecommerce-purchase-api-replica2; do

    ACTUAL_ID="$(
        sudo docker inspect "$container" --format '{{.Image}}'
    )"

    if [[ "$ACTUAL_ID" != "$TARGET_ID" ]]; then
        echo "ERROR: unexpected image in $container"
        exit 1
    fi
done

DEPLOY_SUCCESS=1
trap - EXIT

echo "SUCCESS: rolling deployment completed"
