"""Strict subset of the OpenAI Chat Completions request schema shipped in v1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PublicChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class StreamOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_usage: bool = False


class ChatCompletionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=128)
    messages: list[PublicChatMessage] = Field(min_length=1)
    stream: bool = False
    stream_options: StreamOptions | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1)
    stop: str | list[str] | None = None
    seed: int | None = None
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    user: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _stream_options_require_stream(self):
        if self.stream_options is not None and not self.stream:
            raise ValueError("stream_options may only be set when stream is true")
        if isinstance(self.stop, list) and (not self.stop or len(self.stop) > 4):
            raise ValueError("stop must contain between 1 and 4 strings")
        return self

    def upstream_extra(self, *, disable_thinking: bool) -> dict:
        fields = (
            "temperature",
            "top_p",
            "max_tokens",
            "stop",
            "seed",
            "frequency_penalty",
            "presence_penalty",
        )
        data = {name: getattr(self, name) for name in fields if getattr(self, name) is not None}
        if disable_thinking:
            data["chat_template_kwargs"] = {"enable_thinking": False}
        return data

