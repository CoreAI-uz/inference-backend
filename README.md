# CoreAI Chat and Inference API

CoreAI's chat application and developer API. The platform provides anonymous chat trials,
registered chat history, Google and password sign-in, API keys, shared usage limits, streaming
responses, and account-level usage reporting.

## Architecture

```text
Browser ──► Next.js ──► FastAPI ──► LiteLLM ──► vLLM workers
                       │    │
                       │    └──── Redis
                       └───────── PostgreSQL
```

The web application is served at `chat.coreai.uz`. The public developer API is served at
`api.coreai.uz/v1`. The GPU workers run separately and are reachable only through an SSH tunnel in
local development or a private network in production.

## Requirements

- Docker Engine or Docker Desktop with Docker Compose v2
- SSH access to the inference VM for real-model local development
- The vLLM worker API key
- A Google Web client ID when testing Google sign-in

## Run locally

1. Create `.env` with the worker credential and, when needed, the Google Web client ID:

   ```bash
   VLLM_API_KEY=replace-with-the-worker-key
   GOOGLE_CLIENT_ID=replace-with-the-google-web-client-id
   ```

   `GOOGLE_CLIENT_ID` can be omitted when Google sign-in is not being tested.

3. Start the two inference-worker forwards in a separate terminal:

   ```bash
   ssh -N -T \
     -o ControlMaster=no \
     -o ControlPath=none \
     -o ExitOnForwardFailure=yes \
     -o ServerAliveInterval=30 \
     -o ServerAliveCountMax=3 \
     -L 127.0.0.1:18001:127.0.0.1:18001 \
     -L 127.0.0.1:18002:127.0.0.1:18002 \
     coreai-vllm
   ```

4. Build and start the application:

   ```bash
   docker compose up -d --build
   ```

Database migrations run automatically before the backend starts.

### Local URLs

| Service | URL |
|---|---|
| Chat and account UI | <http://localhost:3000> |
| Backend liveness | <http://localhost:8008/api/health> |
| Full readiness | <http://localhost:8008/api/health/ready> |
| Fresh inference probe | <http://localhost:8008/api/health/inference> |
| LiteLLM gateway | <http://localhost:14001> |
| MinIO console | <http://localhost:9001> |

`/api/health` checks only the FastAPI process. Use `/api/health/ready` to check PostgreSQL, Redis,
object storage, LiteLLM, and the configured vLLM workers.

## Common commands

```bash
make up-d           # start the development stack
make logs           # follow service logs
make ps             # show container health
make migrate        # apply migrations manually
make lint            # backend Ruff checks
make test            # backend test suite
make compat-python   # Python client smoke test against /v1
make compat-node     # JavaScript client smoke test against /v1
make down            # stop containers and keep data
```

For a fresh dependency install outside Docker:

```bash
cd frontend && npm ci
cd ../backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

## Production deployment

The production Compose stack, Caddy routing, environment template, preflight validation, backup
commands, and release checklist are in [deploy/README.md](deploy/README.md).

```bash
cd deploy
cp .env.prod.example .env.prod
# Replace every CHANGE_ME value and set the private worker routes.
./preflight.sh
docker compose --env-file .env.prod -f compose.production.yml up -d --build
```

Only Caddy publishes host ports in production. PostgreSQL, Redis, MinIO, LiteLLM, the backend, and
the frontend remain on the internal Docker network.

## Documentation

- [API quickstart](docs/api-quickstart.md)
- [API v1 contract](docs/openai-compatible-api-v1.md)
- [Google sign-in setup](docs/google-auth-setup.md)
- [Inference connectivity](docs/inference-gateway.md)
- [Deployment guide](deploy/README.md)

## Repository layout

```text
backend/        FastAPI application, migrations, workers, and tests
frontend/       Next.js application and localized copy
litellm/        Development and production model routing
compatibility/  Python and JavaScript API smoke clients
deploy/         Production Compose stack, Caddy, and environment template
docs/           API, authentication, and operations documentation
```

## Secrets and local data

- `.env` and `deploy/.env.prod` are ignored by Git. The production template contains placeholders
  only.
- Never commit API keys, OAuth credentials, database passwords, or signing secrets.
- Docker volumes contain local PostgreSQL, Redis, MinIO, and Caddy state. `make down` keeps them;
  `make down-v` permanently removes them.
- The design handoff and its ZIP archive are local references and are excluded from Git.
