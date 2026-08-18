#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

env_file="${1:-.env.prod}"
compose_file="compose.production.yml"

if [[ ! -f "$env_file" ]]; then
  echo "error: $env_file does not exist; copy .env.prod.example first." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "error: Docker is not installed." >&2
  exit 1
fi

read_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$env_file"
}

required=(
  SITE_ADDRESS
  API_SITE_ADDRESS
  ACME_EMAIL
  POSTGRES_PASSWORD
  DATABASE_URL
  MINIO_ROOT_PASSWORD
  MINIO_SECRET_KEY
  LITELLM_MASTER_KEY
  GEMMA_INFERENCE_BASE_URL
  QWEN_INFERENCE_BASE_URL
  VLLM_API_KEY
  MODELS_CONFIG
  SESSION_SECRET
  JWT_SECRET
  API_KEY_PEPPER
  GOOGLE_CLIENT_ID
)

failed=0
for key in "${required[@]}"; do
  value="$(read_value "$key")"
  if [[ -z "$value" || "$value" == *CHANGE_ME* ]]; then
    echo "error: $key is missing or still uses a placeholder." >&2
    failed=1
  fi
done

secret_keys=(
  POSTGRES_PASSWORD
  MINIO_ROOT_PASSWORD
  MINIO_SECRET_KEY
  LITELLM_MASTER_KEY
  VLLM_API_KEY
  SESSION_SECRET
  JWT_SECRET
  API_KEY_PEPPER
)

for key in "${secret_keys[@]}"; do
  value="$(read_value "$key")"
  if [[ -n "$value" && "$value" != *CHANGE_ME* ]] && (( ${#value} < 24 )); then
    echo "error: $key must contain at least 24 characters." >&2
    failed=1
  fi
done

if [[ "$(read_value MINIO_ROOT_PASSWORD)" != "$(read_value MINIO_SECRET_KEY)" ]]; then
  echo "error: MINIO_ROOT_PASSWORD and MINIO_SECRET_KEY must match." >&2
  failed=1
fi

if [[ "$(read_value SESSION_SECRET)" == "$(read_value JWT_SECRET)" ||
      "$(read_value SESSION_SECRET)" == "$(read_value API_KEY_PEPPER)" ||
      "$(read_value JWT_SECRET)" == "$(read_value API_KEY_PEPPER)" ]]; then
  echo "error: SESSION_SECRET, JWT_SECRET, and API_KEY_PEPPER must be different." >&2
  failed=1
fi

for key in GEMMA_INFERENCE_BASE_URL QWEN_INFERENCE_BASE_URL; do
  value="$(read_value "$key")"
  if [[ -n "$value" && "$value" != *CHANGE_ME* &&
        "$value" != http://* && "$value" != https://* ]]; then
    echo "error: $key must be an http:// or https:// URL." >&2
    failed=1
  fi
done

if [[ "$(read_value APP_ENV)" != "production" ]]; then
  echo "error: APP_ENV must be production." >&2
  failed=1
fi

if [[ "$(read_value DEBUG)" != "false" ]]; then
  echo "error: DEBUG must be false." >&2
  failed=1
fi

if [[ "$(read_value COOKIE_SECURE)" != "true" ]]; then
  echo "error: COOKIE_SECURE must be true." >&2
  failed=1
fi

if (( failed )); then
  exit 1
fi

docker compose --env-file "$env_file" -f "$compose_file" config --quiet
echo "Production configuration passed preflight checks."
