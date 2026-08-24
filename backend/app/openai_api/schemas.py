"""Strict subset of the OpenAI Chat Completions request schema shipped in v1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ReasoningEffort = Literal["none", "low", "medium", "xhigh"]


class FunctionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    strict: bool | None = None


class ChatCompletionTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["function"] = "function"
    function: FunctionDefinition


class ToolChoiceFunction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class ToolChoiceObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["function"] = "function"
    function: ToolChoiceFunction


class ToolCallFunction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    arguments: str


class AssistantToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    type: Literal["function"] = "function"
    function: ToolCallFunction


class PublicChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[AssistantToolCall] | None = None
    tool_call_id: str | None = Field(default=None, min_length=1, max_length=128)
    # ``reasoning`` is CoreAI's public response/input field. The alternate name is
    # accepted for clients that replay a response from another compatible provider.
    reasoning: str | None = None
    reasoning_content: str | None = None

    @model_validator(mode="after")
    def _valid_message_shape(self):
        if self.reasoning is not None and self.reasoning_content is not None:
            raise ValueError("use either reasoning or reasoning_content, not both")
        if self.role != "assistant" and (
            self.reasoning is not None or self.reasoning_content is not None
        ):
            raise ValueError("reasoning may only be supplied on assistant messages")
        if self.role in {"system", "user"}:
            if self.content is None:
                raise ValueError(f"content is required for {self.role} messages")
            if self.tool_calls is not None or self.tool_call_id is not None:
                raise ValueError(f"tool fields are not valid on {self.role} messages")
        elif self.role == "assistant":
            if self.content is None and not self.tool_calls:
                raise ValueError("assistant messages require content or tool_calls")
            if self.tool_call_id is not None:
                raise ValueError("tool_call_id is only valid on tool messages")
        elif self.role == "tool":
            if self.content is None:
                raise ValueError("content is required for tool messages")
            if self.tool_call_id is None:
                raise ValueError("tool_call_id is required for tool messages")
            if self.tool_calls is not None:
                raise ValueError("tool_calls are only valid on assistant messages")
        return self

    def upstream(self) -> dict[str, Any]:
        message = self.model_dump(
            mode="json",
            exclude_none=True,
            exclude={"reasoning", "reasoning_content"},
        )
        reasoning = self.reasoning if self.reasoning is not None else self.reasoning_content
        if reasoning is not None:
            message["reasoning_content"] = reasoning
        return message


class ReasoningOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    effort: Literal["low", "medium", "xhigh"] | None = None


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
    reasoning_effort: ReasoningEffort | None = None
    reasoning: ReasoningOptions | None = None
    tools: list[ChatCompletionTool] | None = Field(default=None, min_length=1, max_length=128)
    tool_choice: Literal["none", "auto", "required"] | ToolChoiceObject | None = None
    parallel_tool_calls: bool | None = None

    @model_validator(mode="after")
    def _stream_options_require_stream(self):
        if self.stream_options is not None and not self.stream:
            raise ValueError("stream_options may only be set when stream is true")
        if isinstance(self.stop, list) and (not self.stop or len(self.stop) > 4):
            raise ValueError("stop must contain between 1 and 4 strings")
        if self.reasoning_effort is not None and self.reasoning is not None:
            raise ValueError("use either reasoning_effort or reasoning, not both")
        if self.reasoning is not None and not self.reasoning.enabled and self.reasoning.effort:
            raise ValueError("reasoning.effort cannot be set when reasoning.enabled is false")
        if self.tool_choice not in (None, "none") and not self.tools:
            raise ValueError("tools are required when tool_choice requests a tool")
        if self.parallel_tool_calls is not None and not self.tools:
            raise ValueError("tools are required when parallel_tool_calls is set")
        if isinstance(self.tool_choice, ToolChoiceObject):
            available = {tool.function.name for tool in self.tools or []}
            if self.tool_choice.function.name not in available:
                raise ValueError("tool_choice must name a function present in tools")
        return self

    def resolved_reasoning_effort(self, default: ReasoningEffort) -> ReasoningEffort:
        if self.reasoning_effort is not None:
            return self.reasoning_effort
        if self.reasoning is not None:
            if not self.reasoning.enabled:
                return "none"
            return self.reasoning.effort or default
        return default

    def uses_tools(self) -> bool:
        return bool(
            self.tools
            or self.tool_choice is not None
            or self.parallel_tool_calls is not None
            or any(message.role == "tool" or message.tool_calls for message in self.messages)
        )
