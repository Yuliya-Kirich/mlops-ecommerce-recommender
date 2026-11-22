#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

python3 - "$ROOT_DIR/scripts/cd/rolling_deploy.sh" \
    "$TEMP_DIR/rollback.sh" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
start = text.index("rollback() {\n")
end = text.index("\n}\n", start) + 2

Path(sys.argv[2]).write_text(text[start:end] + "\n")
print("SUCCESS: настоящая функция rollback извлечена")
PY

cat > "$TEMP_DIR/scenario.sh" <<'BASH'
#!/usr/bin/env bash
set -euo pipefail

UPDATE_SCRIPT="mock-update"
OLD_IMAGE1="sha256:old-replica1"
OLD_IMAGE2="sha256:old-replica2"

CHANGED1=1
CHANGED2=1
DEPLOY_SUCCESS=0

# Имитируем ошибку восстановления второй реплики.
bash() {
    if [[ "$2" == "api-replica2" ]]; then
        echo "MOCK ERROR: replica2 rollback failed"
        return 1
    fi

    echo "MOCK SUCCESS: replica1 rollback completed"
    return 0
}

# Имитируем исходные Image ID первой и второй реплики.
sudo() {
    if [[ "${1:-}" == "-n" ]]; then
        echo "UNEXPECTED_COMPLETE_CALL" >> "$TEST_LOG"
        return 1
    fi

    case "$3" in
        ecommerce-purchase-api-monitoring)
            echo "$OLD_IMAGE1"
            ;;
        ecommerce-purchase-api-replica2)
            echo "sha256:unexpected-image"
            ;;
        *)
            return 1
            ;;
    esac
}

# Имитируем недоступность второй реплики.
check_health() {
    if [[ "$1" == "http://127.0.0.1:8003/health" ]]; then
        echo "MOCK ERROR: replica2 unhealthy"
        return 1
    fi

    return 0
}

stop_active_update() {
    return 0
}

export TEST_LOG="$2"
source "$1"

trap rollback EXIT

echo "EXPECTED: имитируем ошибку deployment"
false
BASH

echo "=== Запускаем сценарий неуспешного отката ==="

if bash "$TEMP_DIR/scenario.sh" "$TEMP_DIR/rollback.sh" "$TEMP_DIR/actions.log" \
    > "$TEMP_DIR/output.log" 2>&1; then

    cat "$TEMP_DIR/output.log"
    echo "ERROR: сбой ошибочно завершился успешно"
    exit 1
fi

cat "$TEMP_DIR/output.log"

echo "=== Проверяем обнаружение аварийного состояния ==="

grep -q \
    "CRITICAL: rollback incomplete; manual recovery required" \
    "$TEMP_DIR/output.log"

grep -q \
    "ERROR: replica2 image was not restored" \
    "$TEMP_DIR/output.log"

grep -q \
    "ERROR: healthcheck failed on port 8003" \
    "$TEMP_DIR/output.log"

if [[ -f "$TEMP_DIR/actions.log" ]] &&
   grep -q "UNEXPECTED_COMPLETE_CALL" "$TEMP_DIR/actions.log"; then
    echo "ERROR: complete called after failed rollback"
    exit 1
fi

echo "SUCCESS: complete was not called"

echo "SUCCESS: неуспешный rollback корректно обнаружен"
echo "SUCCESS: deployment завершился с ошибкой"
