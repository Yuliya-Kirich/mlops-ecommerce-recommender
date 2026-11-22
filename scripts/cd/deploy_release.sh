#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "ERROR: expected Git commit SHA"
    exit 2
fi

COMMIT_SHA="$1"

if [[ ! "$COMMIT_SHA" =~ ^[a-f0-9]{40}$ ]]; then
    echo "ERROR: invalid Git commit SHA"
    exit 2
fi

ROOT="/opt/mlops-cd"
IMAGE="cr.yandex/crp2g9e8cdlnstpbrr5n/ecommerce-purchase-api:$COMMIT_SHA"

echo "=== Acquiring deployment lock ==="

exec 9>/run/mlops-cd/locks/mlops-api-cd.lock

if ! flock -n 9; then
    echo "ERROR: another deployment is running"
    exit 1
fi

export CD_LOCK_INHERITED=1

echo "=== Checking for unfinished deployment ==="

sudo -n /usr/bin/python3 -B     "$ROOT/scripts/cd/deployment_state.py" check


echo "=== Starting CD for commit $COMMIT_SHA ==="

echo "=== Verifying GitHub CI ==="

/usr/bin/python3 -B \
    "$ROOT/scripts/cd/verify_github_ci.py" \
    "$COMMIT_SHA"

echo "=== Pulling Docker image ==="

bash "$ROOT/scripts/cd/pull_image.sh" "$COMMIT_SHA"

echo "=== Starting rolling deployment ==="

CD_COMMIT_SHA="$COMMIT_SHA" \
CD_IMAGE="$IMAGE" \
CD_CONFIRM_DEPLOY=YES \
bash "$ROOT/scripts/cd/rolling_deploy.sh" --deploy

echo "SUCCESS: CD deployment completed"
