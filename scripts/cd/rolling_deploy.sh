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

if [[ "$MODE" == "--deploy" ]]; then
    if [[ ! "${CD_COMMIT_SHA:-}" =~ ^[a-f0-9]{40}$ ]]; then
        echo "ERROR: invalid or missing CD_COMMIT_SHA"
        exit 2
    fi
fi

cd "$ROOT_DIR"

if [[ "$MODE" == "--deploy" ]]; then
    if [[ "${CD_LOCK_INHERITED:-}" == "1" ]]; then
        # Используем файловый дескриптор, полученный от родителя.
        if [[ ! -e /proc/$$/fd/9 ]]; then
            echo "ERROR: inherited lock descriptor is missing"
            exit 1
        fi

        LOCK_FILE="/run/mlops-cd/locks/mlops-api-cd.lock"

        EXPECTED_ID="$(stat -Lc '%d:%i' "$LOCK_FILE")"
        ACTUAL_ID="$(stat -Lc '%d:%i' /proc/$$/fd/9)"

        if [[ "$ACTUAL_ID" != "$EXPECTED_ID" ]]; then
            echo "ERROR: inherited descriptor points to wrong lock file"
            exit 1
        fi

        if ! flock -n 9; then
            echo "ERROR: inherited deployment lock is unavailable"
            exit 1
        fi
    else
        # Самостоятельный запуск rolling deployment.
        exec 9>/run/mlops-cd/locks/mlops-api-cd.lock

        if ! flock -n 9; then
            echo "ERROR: another deployment is running"
            exit 1
        fi
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
ACTIVE_CHILD_PID=""

run_update() {
    local child_status
    local child_pid

    setsid bash "$UPDATE_SCRIPT" "$@" 9>&- &
    child_pid=$!
    ACTIVE_CHILD_PID="$child_pid"

    if wait "$child_pid"; then
        child_status=0
    else
        child_status=$?
    fi

    # An exited leader does not guarantee that its descendants exited.
    if kill -0 -- "-$child_pid" 2>/dev/null; then
        echo "ERROR: update process group is still present"
        return 1
    fi

    # Preserve the PID on failure so rollback can inspect the group.
    if [[ "$child_status" -ne 0 ]]; then
        echo "ERROR: update failed with exit code $child_status"
        return "$child_status"
    fi

    ACTIVE_CHILD_PID=""
    return 0
}

stop_active_update() {
    local child_pid="$ACTIVE_CHILD_PID"
    local attempt

    if [[ -z "$child_pid" ]]; then
        return 0
    fi

    echo "=== Stopping active update process group ==="

    kill -TERM -- "-$child_pid" 2>/dev/null || true

    for attempt in {1..10}; do
        if ! kill -0 -- "-$child_pid" 2>/dev/null; then
            wait "$child_pid" 2>/dev/null || true
            ACTIVE_CHILD_PID=""
            echo "SUCCESS: update process group stopped"
            return 0
        fi
        sleep 1
    done

    echo "WARNING: update group did not stop after SIGTERM"
    echo "=== Sending SIGKILL to remaining group processes ==="

    kill -KILL -- "-$child_pid" 2>/dev/null || true

    for attempt in {1..5}; do
        if ! kill -0 -- "-$child_pid" 2>/dev/null; then
            wait "$child_pid" 2>/dev/null || true
            ACTIVE_CHILD_PID=""
            echo "SUCCESS: update process group terminated"
            return 0
        fi
        sleep 1
    done

    echo "CRITICAL: update process group may still be running"
    return 1
}


rollback() {
    local original_status=$?
    local failed=0
    local actual_id

    trap - EXIT TERM INT

    if ! stop_active_update; then
        echo "CRITICAL: rollback blocked; manual recovery required"
        exit 1
    fi

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
        echo "=== Verifying and completing rollback ==="

        if ! sudo -n python3 "$ROOT_DIR/scripts/cd/deployment_state.py" complete \
            --result rolled_back; then
            echo "CRITICAL: rollback state verification failed"
            echo "Manual recovery required; deployment marker preserved"
            exit 1
        fi

        echo "SUCCESS: rollback completed and verified"
    else
        echo "CRITICAL: rollback incomplete; manual recovery required"
        exit 1
    fi

    if [[ "$original_status" -eq 0 ]]; then
        echo "ERROR: deployment did not complete successfully"
        exit 1
    fi

    exit "$original_status"
}

echo "=== Creating persistent deployment marker ==="

sudo -n python3 "$ROOT_DIR/scripts/cd/deployment_state.py" begin \
    --commit-sha "$CD_COMMIT_SHA" \
    --old-image1 "$OLD_IMAGE1" \
    --old-image2 "$OLD_IMAGE2" \
    --target-id "$TARGET_ID"

trap rollback EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

if [[ "$OLD_IMAGE1" != "$TARGET_ID" ]]; then
    echo "=== Обновляем первую реплику ==="

    CHANGED1=1

    run_update \
        api-replica1 "$TARGET_IMAGE" deploy

    check_health "http://127.0.0.1:8004/health"
else
    echo "Replica 1 already uses target image"
fi

if [[ "$OLD_IMAGE2" != "$TARGET_ID" ]]; then
    echo "=== Обновляем вторую реплику ==="

    CHANGED2=1

    run_update \
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

echo "=== Verifying and completing deployment ==="

# Do not trigger rollback if completion or marker cleanup fails.
# The deployed state must be inspected before manual recovery.
trap - EXIT

if ! sudo -n python3 "$ROOT_DIR/scripts/cd/deployment_state.py" complete \
    --result deployed; then
    echo "CRITICAL: deployment completion verification failed"
    echo "Manual recovery required; inspect deployment state"
    exit 1
fi

DEPLOY_SUCCESS=1

echo "SUCCESS: rolling deployment completed"
