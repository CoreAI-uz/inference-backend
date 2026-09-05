"""Model registry — the ``model_id -> endpoint`` routing map.

This is the seam that lets routing be extracted into a standalone service later
(brief §2). For now it reads the validated ``MODELS_CONFIG`` map off ``Settings``.
"""

from __future__ import annotations

from app.core.config import ModelConfig, Settings, get_settings


class ModelNotFoundError(KeyError):
    """Raised when a request references a model id that isn't configured/enabled."""


class ModelRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def _models(self) -> dict[str, ModelConfig]:
        return self._settings.models_config

    def list_enabled(self) -> list[tuple[str, ModelConfig]]:
        return [(mid, cfg) for mid, cfg in self._models.items() if cfg.enabled]

    def get(self, model_id: str | None) -> tuple[str, ModelConfig]:
        mid = model_id or self._settings.resolve_default_model_id()
        if mid is None:
            raise ModelNotFoundError("no model specified and no default configured")
        cfg = self._models.get(mid)
        if cfg is None:
            matches = [(key, value) for key, value in self._models.items() if mid in value.aliases]
            if len(matches) == 1:
                mid, cfg = matches[0]
        if cfg is None or not cfg.enabled:
            raise ModelNotFoundError(mid)
        return mid, cfg


def get_registry() -> ModelRegistry:
    return ModelRegistry()
