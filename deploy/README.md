# Production deployment

This directory packages the public chat application and developer API for a single Linux VM.
Caddy terminates TLS and routes:

- `chat.coreai.uz` to Next.js, with `/api/*` sent to FastAPI;
- `api.coreai.uz/v1/*` directly to FastAPI.

PostgreSQL, Redis, MinIO, LiteLLM, FastAPI, and Next.js are not published on host ports.

## Files

- `compose.production.yml` — production services, health checks, migrations, restart policies, and
  persistent volumes.
- `Caddyfile` — HTTPS and request routing.
- `.env.prod.example` — complete production configuration template.
- `preflight.sh` — checks required values and validates the Compose configuration.
- `docker-compose.inference-worker.yml` — vLLM-only stack for the separate GPU host.

## VM requirements

- A supported Linux distribution with Docker Engine and Docker Compose v2
- Ports `80/tcp` and `443/tcp` open to the internet
- DNS records for `chat.coreai.uz` and `api.coreai.uz` pointing to the VM
- SSH access from the application VM to the GPU VM
- Enough persistent disk for PostgreSQL, Redis, MinIO, and Caddy data

The production stack maintains an SSH tunnel inside its private Docker network. The GPU VM keeps
both vLLM ports bound to loopback.

## Configure

```bash
cd deploy
cp .env.prod.example .env.prod
chmod 600 .env.prod
```

Replace every `CHANGE_ME` value. Important relationships:

- `POSTGRES_PASSWORD` must match the password inside `DATABASE_URL`.
- `MINIO_ROOT_PASSWORD` and `MINIO_SECRET_KEY` must match.
- `LITELLM_MASTER_KEY` is referenced by `MODELS_CONFIG` and is never exposed publicly.
- `VLLM_API_KEY` must match the worker configuration.
- `INFERENCE_SSH_PRIVATE_KEY_PATH` must point to the restricted tunnel key on the application VM.
- `INFERENCE_SSH_KNOWN_HOSTS_PATH` must contain the verified GPU VM host key.
- `GOOGLE_CLIENT_ID` must allow `https://chat.coreai.uz` as a JavaScript origin.
- `SESSION_SECRET`, `JWT_SECRET`, and `API_KEY_PEPPER` must be independent random values.

Generate three independent secrets with:

```bash
openssl rand -hex 32
```

Validate the configuration without starting services:

```bash
./preflight.sh
```

The script reports missing keys and placeholders without printing secret values.

## Deploy

```bash
docker compose --env-file .env.prod -f compose.production.yml up -d --build
docker compose --env-file .env.prod -f compose.production.yml ps
```

The one-shot `migrate` service applies all Alembic migrations before FastAPI starts. Caddy waits for
both the frontend and backend health checks.

## Verify

```bash
curl --fail https://chat.coreai.uz/api/health
curl --fail https://chat.coreai.uz/api/health/ready
curl --fail https://chat.coreai.uz/api/health/inference
curl --fail https://api.coreai.uz/v1/models \
  -H "Authorization: Bearer cai_your_test_key"
```

Then verify in the browser:

1. Anonymous chat streams a response.
2. Email registration preserves the anonymous conversation.
3. Google registration reaches the legal-acceptance screen.
4. A registered user can create and revoke an API key.
5. Streaming and non-streaming `/v1/chat/completions` requests record usage.
6. English, Russian, and Uzbek routes render correctly.

## Operations

```bash
# Follow logs
docker compose --env-file .env.prod -f compose.production.yml logs -f --tail=200

# Restart one service
docker compose --env-file .env.prod -f compose.production.yml restart backend

# Pull external images and rebuild application images
docker compose --env-file .env.prod -f compose.production.yml pull
docker compose --env-file .env.prod -f compose.production.yml up -d --build

# Stop without deleting data
docker compose --env-file .env.prod -f compose.production.yml down
```

## PostgreSQL backup

Create a backup directory outside the repository or under the ignored `deploy/backups/` path:

```bash
mkdir -p backups
docker compose --env-file .env.prod -f compose.production.yml exec -T postgres \
  pg_dump -U coreai -d coreai -Fc > "backups/coreai-$(date +%F-%H%M).dump"
```

Back up the MinIO and Caddy volumes according to the VM provider's volume-snapshot procedure. Test
database restore and volume recovery before launch.

## Release checklist

- DNS resolves to the production VM.
- TLS certificates are issued successfully by Caddy.
- `.env.prod` passes `./preflight.sh` and is readable only by the deployment user.
- The inference tunnel is healthy and the vLLM endpoints are not publicly exposed.
- `/api/health/ready` reports `ready` for both models.
- Google OAuth production origin and branding are configured.
- PostgreSQL backups and VM monitoring are active.
- Logs have bounded rotation and do not contain credentials or prompt bodies.
