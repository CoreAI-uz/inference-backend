# Inference gateway architecture

CoreAI owns the only LiteLLM gateway:

```text
OpenAI SDK / web chat
        |
        v
CoreAI FastAPI
  - accounts and cai_ API keys
  - consent and safety policy
  - shared web/API limits
  - chat persistence and durable usage ledger
        |
        | internal LiteLLM credential
        v
CoreAI LiteLLM
  - OpenAI/provider translation
  - aliases, routing, retries, and future fallbacks
        |
        | SSH forwards in development; private network in production
        v
Authenticated raw vLLM workers
```

Public `cai_` credentials terminate at CoreAI and never reach LiteLLM or a GPU worker. CoreAI is
also the source of truth for limits and billing data, so LiteLLM does not run its optional spend
database. The GPU VM contains only Gemma and Qwen vLLM containers. They require `VLLM_API_KEY` and
bind their host ports to loopback:

- Gemma: `127.0.0.1:18001` → container port `8000`
- Qwen: `127.0.0.1:18002` → container port `8000`

The worker definition is tracked in `deploy/docker-compose.inference-worker.yml`. Its previous
gateway Compose is backed up on the VM at
`/home/cloud/inference/deploy/docker-compose.pre-central-litellm-20260810.yml`; the old LiteLLM
Postgres volume is preserved for rollback but no gateway container is running.

## Local development

Open both host-side forwards from the development machine:

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

Then configure and start CoreAI in another terminal:

```bash
touch .env
# Set VLLM_API_KEY to the raw-worker key; never commit .env.
docker compose up --build
```

The development route is:

```text
CoreAI -> local LiteLLM -> host.docker.internal:18001/18002
       -> SSH -> raw Gemma/Qwen vLLM
```

LiteLLM is available for inspection at `http://localhost:14001` with its internal development key,
but application clients should call CoreAI on port `8008`.

## Health checks

- `GET /api/health` is a cheap process-liveness check and does not access dependencies.
- `GET /api/health/inference` forces a fresh one-token completion through every enabled LiteLLM
  route. Use it for explicit diagnostics and deployment gates.
- `GET /api/health/ready` combines Postgres and Redis checks with a briefly cached active
  inference result. Its cache defaults to 20 seconds (`INFERENCE_HEALTH_CACHE_S`).

The active checks detect a stopped SSH tunnel or unreachable raw worker; listing LiteLLM's model
catalogue cannot detect either failure. Readiness returns `503` when no enabled model can infer or
Postgres/Redis is unavailable. If at least one model works, a partial worker outage returns HTTP
`200` with `status: "degraded"` and the per-model failures. MinIO is reported but is non-blocking
while OCR is deferred; an unavailable bucket produces `degraded`, not `503`. Health endpoints do
not mint browser session cookies. Use `/api/health` for frequent container liveness,
`/api/health/ready` for orchestrator readiness, and `/api/health/inference` when a fresh end-to-end
probe is specifically required.

## Production deployment

The staging/production Compose runs LiteLLM beside CoreAI without exposing LiteLLM through Caddy.
Set `GEMMA_INFERENCE_BASE_URL` and `QWEN_INFERENCE_BASE_URL` to the raw vLLM endpoints reachable
over the private network, and use the same `VLLM_API_KEY` configured on the workers. Do not expose
ports `18001` or `18002` publicly.

The public `/v1/chat/completions` route validates CoreAI policy and relays LiteLLM's successful JSON
or SSE response while observing usage for the CoreAI ledger. Browser chat continues to use its
separate persistence-aware SSE protocol.
