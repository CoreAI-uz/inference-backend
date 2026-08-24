# CoreAI OpenAI-Compatible API v1

Status: implementation contract for the first public API release.

## Product boundary

- Base URL: `https://inference-api.coreai.uz/v1`
- Authentication: `Authorization: Bearer cai_...`
- One CoreAI account owns chat history, API keys, consent choices, and shared limits.
- API requests do not create web-chat conversations. Free-tier request and response content is
  retained separately for up to 30 days.
- CoreAI terminates public authentication, policy, and quotas; an internal LiteLLM service owns
  provider translation and model routing. Public API keys never reach LiteLLM or GPU workers.
- OCR, billing, Responses API, embeddings, images, audio, batches, and fine-tuning are later work.

## Endpoints

### `GET /v1/models`

Returns the enabled public model IDs in the standard list envelope:

```json
{
  "object": "list",
  "data": [
    {
      "id": "coreai-model-id",
      "object": "model",
      "created": 0,
      "owned_by": "coreai",
      "capabilities": {
        "reasoning": {
          "supported": true,
          "efforts": ["none", "low", "medium", "xhigh"],
          "default_effort": "xhigh"
        },
        "tools": {
          "supported": true,
          "tool_choice": ["none", "auto", "required"],
          "parallel_tool_calls": true
        }
      }
    }
  ]
}
```

### `POST /v1/chat/completions`

Required fields:

- `model`
- `messages` containing `system`, `user`, `assistant`, or `tool` messages

Supported request fields in v1:

- `stream`
- `stream_options.include_usage`
- `temperature`
- `top_p`
- `max_tokens`
- `stop`
- `seed`
- `frequency_penalty`
- `presence_penalty`
- `user`
- `reasoning_effort`
- `reasoning`
- `tools`
- `tool_choice`
- `parallel_tool_calls`

Unknown fields and known-but-unsupported capabilities are rejected with an
`invalid_request_error`; they are not silently ignored. Structured output, multimodal content,
log probabilities, and multiple choices are not supported.

### Reasoning controls

`qwen3.8-27b` supports these `reasoning_effort` values:

- `none` — answer without a reasoning trace
- `low` — short reasoning
- `medium` — balanced reasoning
- `xhigh` — deep reasoning and the model default

The equivalent object form is `"reasoning": {"enabled": true, "effort": "medium"}`. Set
`enabled` to `false` to disable reasoning. Do not send `reasoning` and `reasoning_effort` together.

Non-streaming responses expose the trace as `choices[0].message.reasoning`. Streaming responses
use `choices[0].delta.reasoning`, separately from `content`. Assistant messages may include
`reasoning` when replaying earlier turns; `reasoning_content` is accepted as an input alias.

Non-streaming responses use `object: "chat.completion"`. Streaming responses contain only
`data: {chat.completion.chunk...}` events followed by `data: [DONE]`. When
`stream_options.include_usage` is true, the final JSON chunk has an empty `choices` array and the
aggregate usage. CoreAI's browser-only `queued`, `reasoning`, and `done` events never appear here.
Additive OpenAI-compatible response fields, including token-detail fields, are preserved.

### Tool calling

`qwen3.8-27b` supports function tools. Each tool uses this shape:

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "Get the current weather for a city",
    "parameters": {
      "type": "object",
      "properties": {"city": {"type": "string"}},
      "required": ["city"]
    }
  }
}
```

`tool_choice` accepts `none`, `auto`, `required`, or
`{"type":"function","function":{"name":"get_weather"}}`. A tool-call response places calls in
`choices[0].message.tool_calls` and uses `finish_reason: "tool_calls"`. Execute each function in
your application, then append the assistant message and one `tool` message per result:

```json
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "content": "{\"temperature_c\":18}"
}
```

For streaming responses, call fragments arrive in `choices[0].delta.tool_calls`. Accumulate them by
`index` and concatenate `function.arguments` in order. The final chunk uses
`finish_reason: "tool_calls"`. `parallel_tool_calls` controls whether one response may contain
multiple calls.

## Errors and observability

Errors use this envelope:

```json
{
  "error": {
    "message": "Human-readable message",
    "type": "invalid_request_error",
    "param": "model",
    "code": "model_not_found"
  }
}
```

Every response includes `x-request-id`. Clients may send `X-Client-Request-Id`, which is logged
after validation and echoed back. Rate-limited responses use HTTP 429, include `Retry-After`, and
publish the applicable `x-ratelimit-*` headers. Upstream unavailability before a stream begins is
HTTP 503; after streaming begins, the connection closes because the HTTP status can no longer be
changed.

## Authentication and keys

- Keys begin with `cai_` and are shown once at creation.
- The database stores a lookup prefix, last four characters, and an HMAC-SHA-256 digest keyed by a
  server-side pepper; it never stores the plaintext key.
- A user may have at most three active keys initially.
- Keys can be named and revoked. Expiry is represented in the schema even if the first UI does not
  expose custom expiry.
- Authentication failures return the same generic response for missing, malformed, unknown,
  revoked, or expired keys.

## Limits and metering

- Web chat and API usage debit the same account allowance.
- `qwen3.8-27b` supports a 262,144-token context window. `gemma4-31b-it` supports 16,384 tokens.
- The model validates the complete prompt against its token context window and returns
  `context_length_exceeded` when the prompt is too large.
- Request-rate enforcement remains a Redis token bucket. Token usage is written to the durable
  `usage_events` ledger with source, API key, request ID, latency, and response status.
- Cached-input and reasoning-token details are copied into their dedicated ledger columns when the
  provider reports them. Cached input is observational for now; it is not a separately priced tier.
- Limits are account-scoped, never key-scoped, so creating another key does not create more quota.
- The first safe rollout may enforce request limits before hourly input/output token budgets are
  enabled; the public headers must reflect only limits that are actually enforced.

## Data policy

- API access requires acceptance of the current Terms of Service and acknowledgement of the
  Privacy Policy.
- Acceptance is recorded as a versioned, append-only event.
- Successful API requests retain the submitted messages and request parameters together with the
  generated response for up to 30 days. Streaming requests retain the assembled response.
- Content records do not include the plaintext API key or request headers and do not appear in the
  developer usage console or web-chat history.
- Expired content is deleted by the scheduled retention sweep. Metering rows remain in the durable
  usage ledger.
- API content is not approved for model training under this policy. Training requires a separate
  policy and consent scope.
- Each usage and content record identifies the policy effective when the request was made.

## Compatibility policy

We preserve request and response fields already shipped within `/v1`. Additive fields are allowed;
breaking behavior requires a new version or a documented deprecation window. Compatibility is
tested with the official OpenAI Python and JavaScript SDKs by changing only `base_url` and API key.
The reusable real-server suite is documented in [`compatibility/README.md`](../compatibility/README.md).
For streams, CoreAI commits the usage ledger before forwarding the terminal `data: [DONE]` frame,
so SDKs that stop consuming at that marker cannot cancel metering.
