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
        }
        for mid, cfg in registry.list_enabled()
    ]
