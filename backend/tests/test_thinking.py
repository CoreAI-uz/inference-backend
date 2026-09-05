"""Gemma toggle controls and provider-compatible request translation."""

import pytest
from pydantic import ValidationError

from app.core.config import ModelConfig, Settings
from app.gateway.registry import ModelNotFoundError, ModelRegistry
from app.openai_api.router import _exclude_reasoning, _upstream_body
from app.openai_api.schemas import ChatCompletionIn


def gemma_config(**overrides):
    return ModelConfig(
        endpoint="http://mock-vllm/v1", served_model_name="gemma-mock",
        display_name="Gemma", supports_thinking=True, reasoning_mode="toggle",
        aliases=["google/gemma-4-31b-it"], **overrides,
    )


@pytest.mark.parametrize("control,enabled", [({}, False), ({"reasoning": {}}, False),
    ({"reasoning": {"enabled": True}}, True), ({"reasoning": {"enabled": False}}, False),
    ({"reasoning": {"enabled": True, "exclude": True}}, True),
    ({"reasoning": {"exclude": True}}, False)])
def test_toggle_translation(control, enabled):
    cfg = gemma_config()
    request = ChatCompletionIn(model="google/gemma-4-31b-it",
        messages=[{"role": "user", "content": "Hello"}], **control)
    body = _upstream_body(request, cfg)
    assert body["chat_template_kwargs"] == {"enable_thinking": enabled}
    assert "reasoning_effort" not in body and "reasoning" not in body
    assert cfg.reasoning_efforts == []
    assert cfg.default_reasoning_effort == "none"


def test_standard_message_and_output_limit_translation():
    request = ChatCompletionIn(model="gemma", max_completion_tokens=128,
        messages=[{"role": "developer", "content": [{"type": "text", "text": "Be concise."}]},
                  {"role": "user", "content": [{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}]}])
    body = _upstream_body(request, gemma_config())
    assert body["max_tokens"] == 128 and "max_completion_tokens" not in body
    assert body["messages"] == [{"role": "system", "content": "Be concise."}, {"role": "user", "content": "Hello world"}]
    with pytest.raises(ValidationError):
        ChatCompletionIn(**{**request.model_dump(), "max_tokens": 42})


def test_alias_resolves_only_available_model():
    settings = Settings(models_config={"gemma": gemma_config()})
    assert ModelRegistry(settings).get("google/gemma-4-31b-it")[0] == "gemma"
    settings.models_config["gemma"].enabled = False
    with pytest.raises(ModelNotFoundError):
        ModelRegistry(settings).get("google/gemma-4-31b-it")


def test_exclusion_keeps_answer_and_usage():
    response = {"choices": [{"message": {"content": "42", "reasoning": "private", "reasoning_details": []}}],
                "usage": {"completion_tokens_details": {"reasoning_tokens": 12}}}
    filtered = _exclude_reasoning(response)
    assert filtered["choices"][0]["message"] == {"content": "42"}
    assert filtered["usage"]["completion_tokens_details"]["reasoning_tokens"] == 12
