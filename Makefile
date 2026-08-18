.PHONY: up up-d down down-v build rebuild logs ps stop restart tunnel migrate revision downgrade fmt lint test frontend-check compose-check prod-check shell psql redis-cli compat-python compat-node

up:            ## Build (if needed) and start the whole stack
	docker compose up --build

up-d:          ## Same, detached
	docker compose up --build -d

down:          ## Stop and remove containers (keeps volumes)
	docker compose down

down-v:        ## Stop and remove containers AND volumes (wipes data)
	docker compose down -v

build:
	docker compose build

rebuild:
	docker compose build --no-cache

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

stop:
	docker compose stop

restart:
	docker compose restart backend

tunnel:         ## Forward the two local vLLM worker ports (runs in foreground)
	ssh -N -T \
		-o ControlMaster=no -o ControlPath=none \
		-o ExitOnForwardFailure=yes \
		-o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
		-L 127.0.0.1:18001:127.0.0.1:18001 \
		-L 127.0.0.1:18002:127.0.0.1:18002 \
		coreai-vllm

# --- Backend (run inside the backend container) ---
migrate:       ## Apply DB migrations (M2+)
	docker compose run --rm backend alembic upgrade head

revision:      ## Autogenerate a migration: make revision m="message"
	docker compose run --rm backend alembic revision --autogenerate -m "$(m)"

downgrade:     ## Roll back one migration
	docker compose run --rm backend alembic downgrade -1

fmt:
	docker compose run --rm backend ruff format app

lint:
	docker compose run --rm backend ruff check app tests alembic

test:
	docker compose run --rm backend pytest -q

frontend-check: ## Type-check and build the frontend
	docker compose run --rm --no-deps frontend sh -c "npm ci && npx tsc --noEmit && npm run build"

compose-check:  ## Validate the development Compose file
	docker compose config --quiet

prod-check:     ## Validate deploy/.env.prod and production Compose
	cd deploy && ./preflight.sh

compat-python: ## Run real-server compatibility checks with the official Python SDK
	docker compose run --rm --no-deps \
		-e COREAI_BASE_URL=$${COREAI_BASE_URL:-http://backend:8000/v1} \
		-e COREAI_API_KEY -e COREAI_MODEL \
		-v $(CURDIR)/compatibility:/compat \
		backend python /compat/openai_python.py

compat-node:   ## Run real-server compatibility checks with the official JavaScript SDK
	docker run --rm --network coreai-inference_default \
		-v $(CURDIR)/compatibility:/compat -w /compat \
		-e COREAI_BASE_URL=$${COREAI_BASE_URL:-http://backend:8000/v1} \
		-e COREAI_API_KEY -e COREAI_MODEL \
		node:20-alpine sh -c "npm ci --ignore-scripts >/dev/null && npm run smoke --silent"

shell:
	docker compose exec backend bash

psql:
	docker compose exec postgres psql -U coreai -d coreai

redis-cli:
	docker compose exec redis redis-cli
