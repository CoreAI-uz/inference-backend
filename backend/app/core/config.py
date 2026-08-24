"""Application configuration.

A single ``Settings`` object, loaded from environment variables (and an optional
``.env`` file for local, non-Docker runs). ``MODELS_CONFIG`` is parsed and validated
at load time so a malformed model map fails fast at startup rather than on first
request.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    """One entry of the ``model_id -> {...}`` routing map (gateway config)."""

    endpoint: str  # Internal LiteLLM OpenAI-compatible base URL.
    served_model_name: str
    api_key: str | None = None  # sent as "Authorization: Bearer ..." if set
    max_context: int = 8192
    display_name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    # Model can produce a separately parsed reasoning trace.
    supports_thinking: bool = False
    supports_tools: bool = False
    reasoning_efforts: list[Literal["none", "low", "medium", "xhigh"]] = Field(
        default_factory=list
    )
    default_reasoning_effort: Literal["none", "low", "medium", "xhigh"] = "low"
    # Extra request-body params merged into every completion (e.g. per-model sampling).
    extra_body: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reasoning_capabilities(self):
        if self.supports_thinking:
            if not self.reasoning_efforts:
                self.reasoning_efforts = ["none", "low", "medium", "xhigh"]
            if self.default_reasoning_effort not in self.reasoning_efforts:
                raise ValueError("default_reasoning_effort must be listed in reasoning_efforts")
        else:
            self.reasoning_efforts = []
            self.default_reasoning_effort = "none"
        return self

    def resolved_api_key(self) -> str | None:
        """Resolve LiteLLM-style ``os.environ/NAME`` secret references lazily."""
        if self.api_key and self.api_key.startswith("os.environ/"):
            return os.environ.get(self.api_key.removeprefix("os.environ/"))
        return self.api_key


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_env: str = "dev"
    debug: bool = True
    # --- Datastores ---
    database_url: str = "postgresql+asyncpg://coreai:coreai@postgres:5432/coreai"
    redis_url: str = "redis://redis:6379/0"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "ocr-uploads"
    minio_secure: bool = False

    # --- Model routing (gateway) ---
    # Env var MODELS_CONFIG maps here (field name matches, case-insensitive).
    models_config: dict[str, ModelConfig] = Field(default_factory=dict)
    default_model_id: str | None = None

    # --- Identity / cookies (M5+) ---
    session_secret: str = "dev-session-secret-change-me-at-least-32-bytes"
    jwt_secret: str = "dev-jwt-secret-change-me-at-least-32-bytes"
    jwt_alg: str = "HS256"
    access_token_ttl_s: int = 2_592_000  # 30 days
    anon_cookie_ttl_s: int = 2_592_000
    # HMAC key for developer credentials. Production must override this independently
    # from the cookie/JWT secrets so one secret rotation does not invalidate all auth.
    api_key_pepper: str = "dev-api-key-pepper-change-me-at-least-32-bytes"
    max_api_keys_per_user: int = 3
    cookie_secure: bool = False
    google_client_id: str | None = None
    google_pending_ttl_s: int = 600

    # --- HTTP ---
    cors_origins: str = "http://localhost:3000"
    trusted_proxy: bool = False
    # Verify TLS on outbound inference calls. Set false for a self-signed gateway in
    # dev/staging; keep true in prod (or point the client at the gateway's CA cert).
    inference_verify_tls: bool = True
    # Readiness reuses active inference results briefly so orchestrator polling does
    # not generate a completion on every request. The explicit inference endpoint
    # always bypasses this cache.
    inference_health_cache_s: float = 20.0

    # --- Chat limits / safety (M4+) ---
    max_chat_input_chars: int = 24_000
    rl_anon_chat: int = 5
    rl_user_chat: int = 30
    rl_signup_per_ip: int = 5  # account creations per IP (anti-farming)
    rl_login_per_ip: int = 20
    rl_login_per_account: int = 10
    max_queue_wait_s: int = 60
    # Unclaimed anonymous conversations are swept after this many days (registered
    # users' chats persist as their history regardless).
    anon_conv_retention_days: int = 30
    # Free-tier API request and response bodies are removed after this window.
    api_content_retention_days: int = 30
    conv_sweep_interval_s: int = 3600

    # --- Auto-titling ---
    # Name a new conversation from its first message via a one-shot LLM call (ChatGPT
    # style). Off → keep the deterministic trimmed-first-message title.
    auto_title: bool = True
    title_model_id: str | None = None  # None → reuse the conversation's own model
    title_timeout_s: float = 8.0  # hard cap; falls back to the trimmed title

    # --- OCR (dormant; deferred track) ---
    ocr_engine: str = "mock"
    ocr_vllm_endpoint: str | None = None
    ocr_model_id: str | None = None
    ocr_max_file_mb: int = 20
    ocr_max_pages: int = 50
    ocr_retention_hours: int = 24
    ocr_raster_dpi: int = 200
    rl_anon_ocr: int = 1
    rl_user_ocr: int = 10
    sweep_interval_s: int = 900

    # --- Deploy ---
    web_concurrency: int = 4
    allowed_hosts: str = "*"

    @field_validator("models_config", mode="before")
    @classmethod
    def _parse_models_config(cls, v: object) -> object:
        """Accept either a JSON string (from env) or an already-parsed dict."""
        if v is None or v == "":
            return {}
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError as exc:
                raise ValueError(f"MODELS_CONFIG is not valid JSON: {exc}") from exc
        return v

    @field_validator("google_client_id", mode="before")
    @classmethod
    def _blank_google_client_id(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        hosts = [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]
        return hosts or ["*"]

    def resolve_default_model_id(self) -> str | None:
        """The configured default, or the first enabled model, else None."""
        if self.default_model_id and self.default_model_id in self.models_config:
            return self.default_model_id
        for mid, cfg in self.models_config.items():
            if cfg.enabled:
                return mid
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
