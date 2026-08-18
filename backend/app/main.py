"""FastAPI application factory + lifespan.

Lifespan wires the shared clients (Redis, httpx, MinIO) onto ``app.state`` so every
request reuses one pool. ``get_settings()`` is called eagerly so a malformed config
(e.g. bad ``MODELS_CONFIG``) fails fast at startup.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from minio import Minio
from redis.asyncio import Redis
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import api_router
from app.auth.middleware import AnonSessionMiddleware
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.request_log import RequestLogMiddleware
from app.gateway.errors import APIError, api_error_handler
from app.openai_api import router as openai_router
from app.openai_api.errors import (
    OpenAIAPIError,
    openai_error_handler,
    public_validation_error_handler,
)
from app.workers.sweep import sweep_loop

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()  # fail-fast on bad config
    configure_logging(debug=settings.debug)

    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.http = httpx.AsyncClient(
        verify=settings.inference_verify_tls,  # false for a self-signed gateway (dev)
        timeout=httpx.Timeout(connect=5.0, read=None, write=10.0, pool=5.0),
    )
    app.state.minio = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    app.state.inference_health_cache = None
    app.state.inference_health_lock = asyncio.Lock()

    model_ids = list(settings.models_config.keys())
    log.info("startup", app_env=settings.app_env, models=model_ids,
             default_model=settings.resolve_default_model_id())

    sweep_task = asyncio.create_task(sweep_loop(app.state.redis))

    try:
        yield
    finally:
        sweep_task.cancel()
        try:
            await sweep_task
        except asyncio.CancelledError:
            pass
        await app.state.http.aclose()
        await app.state.redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CoreAI Inference", version="0.1.0", lifespan=lifespan)

    # Added inner-first; CORS is added last so it stays outermost (handles preflight).
    # RequestLog is innermost so request.state.session_id (set by AnonSession) is available.
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(AnonSessionMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(OpenAIAPIError, openai_error_handler)
    app.add_exception_handler(RequestValidationError, public_validation_error_handler)
    app.include_router(api_router)
    app.include_router(openai_router)
    return app


app = create_app()
