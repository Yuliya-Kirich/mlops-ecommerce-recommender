#!/usr/bin/env bash
set -euo pipefail

CALLS=()
CHANGED1=0
CHANGED2=0

update_replica() {
    local service="$1"
    local action="$2"

    CALLS+=("$service:$action")

    if [[ "$service" == "api-replica2" &&
          "$action" == "deploy" ]]; then
        return 1
    fi
}

rollback() {
    if [[ "$CHANGED2" == 1 ]]; then
        update_replica api-replica2 rollback || return 1
    fi

    if [[ "$CHANGED1" == 1 ]]; then
        update_replica api-replica1 rollback || return 1
    fi
}

echo "=== Имитируем обновление первой реплики ==="

CHANGED1=1
update_replica api-replica1 deploy

echo "=== Имитируем ошибку второй реплики ==="

CHANGED2=1

if update_replica api-replica2 deploy; then
    echo "ERROR: ожидалась ошибка"
    exit 1
else
    echo "EXPECTED: обновление второй реплики завершилось ошибкой"
fi

echo "=== Имитируем автоматический откат ==="

rollback

printf '%s\n' "${CALLS[@]}"

EXPECTED=(
    "api-replica1:deploy"
    "api-replica2:deploy"
    "api-replica2:rollback"
    "api-replica1:rollback"
)

if [[ "${CALLS[*]}" == "${EXPECTED[*]}" ]]; then
    echo "SUCCESS: порядок отката корректный"
else
    echo "ERROR: неправильный порядок отката"
    exit 1
fi
