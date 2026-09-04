#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
server_dir="$repo_dir/server"
endpoint="${DYNAMODB_LOCAL_ENDPOINT:-http://127.0.0.1:8001}"
manage_local="${MANAGE_DYNAMODB_LOCAL:-1}"

if [[ -x "$repo_dir/.venv/bin/python" ]]; then
  python_cmd="$repo_dir/.venv/bin/python"
elif [[ -x "$server_dir/.venv/bin/python" ]]; then
  python_cmd="$server_dir/.venv/bin/python"
else
  python_cmd="${PYTHON:-python3}"
fi

if [[ "$manage_local" == "1" ]]; then
  CLIENT_GATEWAY_URL="${CLIENT_GATEWAY_URL:-http://localhost:8100/integration/v1}" \
    docker compose -f "$repo_dir/compose.dev.yml" --profile dynamodb up -d dynamodb-local
  trap 'CLIENT_GATEWAY_URL="${CLIENT_GATEWAY_URL:-http://localhost:8100/integration/v1}" docker compose -f "$repo_dir/compose.dev.yml" --profile dynamodb stop dynamodb-local >/dev/null' EXIT
fi

"$python_cmd" - "$endpoint" <<'PY'
import socket
import sys
import time
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
port = parsed.port or (443 if parsed.scheme == "https" else 80)
for attempt in range(30):
    try:
        with socket.create_connection((parsed.hostname, port), timeout=1):
            break
    except OSError:
        if attempt == 29:
            raise SystemExit(f"DynamoDB Local did not become ready at {sys.argv[1]}")
        time.sleep(1)
PY

cd "$server_dir"
DYNAMODB_LOCAL_ENDPOINT="$endpoint" \
AWS_REGION="${AWS_REGION:-ap-southeast-1}" \
AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-localTestKey}" \
AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-localTestSecret}" \
  "$python_cmd" -m pytest -o addopts='' -q "$@"
