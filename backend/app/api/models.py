"""GET /api/models — derived from the gateway registry (MODELS_CONFIG)."""

from __future__ import annotations

from fastapi import APIRouter

from app.gateway.registry import get_registry

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
async def list_models() -> list[dict]:
    registry = get_registry()
    return [
        {
            "id": mid,
            "display_name": cfg.display_name,
            "description": cfg.description,
            "tags": cfg.tags,
            "supports_thinking": cfg.supports_thinking,
            "reasoning_mode": cfg.reasoning_mode,
            "supports_tools": cfg.supports_tools,
            "reasoning_efforts": cfg.reasoning_efforts,
            "default_reasoning_effort": cfg.default_reasoning_effort,
        }
        for mid, cfg in registry.list_enabled()
    ]
