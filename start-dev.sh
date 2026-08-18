#!/usr/bin/env bash
# Boot the full dev stack against the SSH-tunneled real vLLM workers.
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker is required but not installed." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "error: .env is missing; create it and set VLLM_API_KEY." >&2
  exit 1
fi

if command -v nc >/dev/null 2>&1; then
  for port in 18001 18002; do
    if ! nc -z 127.0.0.1 "$port"; then
      echo "error: inference tunnel port $port is closed; run 'make tunnel' first." >&2
      exit 1
    fi
  done
fi

echo "Starting CoreAI Inference dev stack..."
echo "  backend:   http://localhost:8008/api/health"
echo "  frontend:  http://localhost:3000"
echo "  LiteLLM:   http://localhost:14001/v1/models (internal dev key required)"
echo "  MinIO:     http://localhost:9001 (console; minioadmin/minioadmin)"
echo

exec docker compose up --build
