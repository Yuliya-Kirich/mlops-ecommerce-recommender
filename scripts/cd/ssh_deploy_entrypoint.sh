#!/usr/bin/env bash
set -euo pipefail

REQUEST="${SSH_ORIGINAL_COMMAND:-}"

# Принимаем только deploy и полный Git SHA.
if [[ ! "$REQUEST" =~ ^deploy[[:space:]]([a-f0-9]{40})$ ]]; then
    echo "ERROR: команда не разрешена"
    exit 2
fi

COMMIT_SHA="${BASH_REMATCH[1]}"

# Клиент установлен в защищённом системном каталоге.
exec /usr/bin/python3 -B \
    /usr/local/libexec/mlops-cd/socket_client.py \
    "$COMMIT_SHA"
