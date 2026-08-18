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
      "owned_by": "coreai"
    }
  ]
}
```

### `POST /v1/chat/completions`

Required fields:

- `model`
- `messages` containing text-only `system`, `user`, or `assistant` messages

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

Unknown fields and known-but-unsupported capabilities are rejected with an
`invalid_request_error`; they are not silently ignored. The first release does not support tool
calls, structured output, multimodal content, log probabilities, multiple choices, or exposing
model reasoning.

Non-streaming responses use `object: "chat.completion"`. Streaming responses contain only
`data: {chat.completion.chunk...}` events followed by `data: [DONE]`. When
`stream_options.include_usage` is true, the final JSON chunk has an empty `choices` array and the
aggregate usage. CoreAI's browser-only `queued`, `reasoning`, and `done` events never appear here.
Successful JSON and SSE payloads are relayed from LiteLLM so additive OpenAI-compatible response
fields (for example token-detail fields) are preserved.

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
