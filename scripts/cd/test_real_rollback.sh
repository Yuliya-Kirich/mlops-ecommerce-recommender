#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

export TEST_LOG="$TEMP_DIR/actions.log"
touch "$TEST_LOG"

# Извлекаем реальную функцию из рабочего CD-скрипта.
python3 - "$ROOT_DIR/scripts/cd/rolling_deploy.sh" \
    "$TEMP_DIR/rollback.sh" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()

start = text.index("rollback() {\n")
end = text.index("\n}\n", start) + 2

Path(sys.argv[2]).write_text(text[start:end] + "\n")

print("SUCCESS: функция rollback извлечена")
PY

cat > "$TEMP_DIR/scenario.sh" <<'BASH'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/tmp/mlops-test-isolated"
UPDATE_SCRIPT="mock-update"
OLD_IMAGE1="sha256:old-replica1"
OLD_IMAGE2="sha256:old-replica2"

CHANGED1=1
CHANGED2=1
DEPLOY_SUCCESS=0

# Заглушка вместо запуска обновления.
bash() {
    printf 'UPDATE %s %s %s\n' "$2" "$3" "$4" >> "$TEST_LOG"
}

# Заглушка вместо docker inspect.
sudo() {
    if [[ "${1:-}" == "-n" && "${2:-}" == "python3" ]]; then
        if [[ "${4:-}" == "complete" &&
              "${5:-}" == "--result" &&
              "${6:-}" == "rolled_back" ]]; then
            echo "COMPLETE rolled_back" >> "$TEST_LOG"
            return 0
        fi
        echo "ERROR: unexpected deployment state command" >&2
        return 1
    fi
    case "$3" in
        ecommerce-purchase-api-monitoring)
            echo "$OLD_IMAGE1"
            ;;
        ecommerce-purchase-api-replica2)
            echo "$OLD_IMAGE2"
            ;;
        *)
            return 1
            ;;
    esac
}

# Заглушка вместо HTTP-запросов.
check_health() {
    printf 'HEALTH %s\n' "$1" >> "$TEST_LOG"
    return 0
}

stop_active_update() {
    return 0
}

source "$1"

trap rollback EXIT

echo "EXPECTED: имитируем ошибку развёртывания"
false
BASH

echo "=== Запускаем изолированный сценарий ==="

if bash "$TEMP_DIR/scenario.sh" "$TEMP_DIR/rollback.sh" \
    > "$TEMP_DIR/output.log" 2>&1; then
    cat "$TEMP_DIR/output.log"
    echo "ERROR: после сбоя получен успешный код завершения"
    exit 1
else
    cat "$TEMP_DIR/output.log"
    echo "SUCCESS: ошибка развёртывания не скрыта"
fi

echo "=== Проверяем фактический порядок действий ==="

cat "$TEST_LOG"

cat > "$TEMP_DIR/expected.log" <<'EXPECTED'
UPDATE api-replica2 sha256:old-replica2 deploy
UPDATE api-replica1 sha256:old-replica1 deploy
HEALTH http://127.0.0.1:8002/health
HEALTH http://127.0.0.1:8003/health
HEALTH http://127.0.0.1:8004/health
COMPLETE rolled_back
EXPECTED

diff -u "$TEMP_DIR/expected.log" "$TEST_LOG"

grep -q \
    "SUCCESS: rollback completed and verified" \
    "$TEMP_DIR/output.log"

echo "SUCCESS: настоящая функция rollback прошла тест"

echo "=== Проверяем Git ==="
git status -sb
