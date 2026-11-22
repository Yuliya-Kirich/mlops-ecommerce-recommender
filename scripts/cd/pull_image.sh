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

IMAGE="cr.yandex/crp2g9e8cdlnstpbrr5n/ecommerce-purchase-api:$COMMIT_SHA"

DOCKER_CONFIG="$(mktemp -d /run/mlops-cd/docker-auth.XXXXXX)"
export DOCKER_CONFIG

chmod 700 "$DOCKER_CONFIG"

trap 'rm -rf "$DOCKER_CONFIG"' EXIT

echo "=== Authenticating to Container Registry ==="

python3 - <<'PY' | docker login \
    --username iam \
    --password-stdin \
    cr.yandex
import json
import urllib.request

url = (
    "http://169.254.169.254/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)

request = urllib.request.Request(
    url,
    headers={"Metadata-Flavor": "Google"},
)

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)

with opener.open(request, timeout=10) as response:
    data = json.load(response)

print(data["access_token"])
PY

echo "=== Pulling verified image tag ==="

docker pull "$IMAGE"

echo "=== Checking downloaded image ==="

docker image inspect "$IMAGE" --format 'Image ID: {{.Id}}'

echo "SUCCESS: Docker image downloaded"
