"""Internal gateway client for browser chat.

Consumes LiteLLM's OpenAI-compatible streaming endpoint and yields parsed chunks.
LiteLLM, rather than this client, selects the mock or real vLLM worker.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx

from app.core.config import ModelConfig


@dataclass
class ChatChunk:
    content: str | None
    reasoning: str | None
    finish_reason: str | None
    usage: dict | None


class VLLMClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def stream_chat(
        self,
        cfg: ModelConfig,
        messages: list[dict],
        *,
        extra: dict | None = None,
        headers: dict | None = None,
    ) -> AsyncGenerator[ChatChunk, None]:
        url = f"{cfg.endpoint.rstrip('/')}/chat/completions"
        payload: dict = {
            "model": cfg.served_model_name,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if cfg.extra_body:
            payload.update(cfg.extra_body)
        if extra:
            payload.update(extra)

        req_headers = dict(headers or {})
        if api_key := cfg.resolved_api_key():
            req_headers["Authorization"] = f"Bearer {api_key}"

        async with self._http.stream(
            "POST", url, json=payload, headers=req_headers or None
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    return
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue

                content: str | None = None
                reasoning: str | None = None
                finish: str | None = None
                choices = obj.get("choices") or []
                if choices:
                    ch0 = choices[0]
                    delta = ch0.get("delta") or {}
                    content = delta.get("content")
                    # vLLM emits parsed thinking under ``reasoning``. Accept the
                    # alternate name as well so the gateway remains portable across
                    # OpenAI-compatible inference servers.
                    reasoning = delta.get("reasoning")
                    if reasoning is None:
                        reasoning = delta.get("reasoning_content")
                    finish = ch0.get("finish_reason")

                yield ChatChunk(
                    content=content,
                    reasoning=reasoning,
                    finish_reason=finish,
                    usage=obj.get("usage"),
                )
