"""Aggregates all sub-routers under the /api prefix."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import chat, conversations, developer, health, models
from app.auth import router as auth_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth_router.router)
api_router.include_router(models.router)
api_router.include_router(chat.router)
api_router.include_router(conversations.router)
api_router.include_router(developer.router)

# Future routers (ocr) are included here as they land.
