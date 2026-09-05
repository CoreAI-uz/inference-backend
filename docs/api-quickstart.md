# CoreAI API quickstart

Documentation and account management are available at:

- Product docs: `https://chat.coreai.uz/docs`
- Keys and usage: `https://chat.coreai.uz/console`

Base URL: `https://inference-api.coreai.uz/v1`

Model: `google/gemma-4-31b-it`

Authentication: `Authorization: Bearer cai_...`

Create a key while signed in to the [CoreAI developer console](https://chat.coreai.uz/console).
Copy it immediately: the plaintext value is shown once and cannot be recovered later. The console
also shows the shared chat/API allowance and aggregate token usage by source and model; it never
displays prompt or response content in the usage view.

Free-tier API prompts, request parameters, and generated responses are retained for up to 30 days
and may be reviewed to evaluate quality, understand usage, and prevent abuse. Accept the current
Terms of Service in the console before creating or using an API key.

## Python using HTTP directly

```bash
pip install requests
export COREAI_API_KEY="cai_..."
```

```python
import os
import requests

response = requests.post(
    "https://inference-api.coreai.uz/v1/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['COREAI_API_KEY']}"},
    json={
        "model": "google/gemma-4-31b-it",
        "messages": [{"role": "user", "content": "Salom!"}],
    },
)
response.raise_for_status()
print(response.json()["choices"][0]["message"]["content"])
```

## Python with the OpenAI SDK

```bash
pip install openai
export COREAI_API_KEY="cai_..."
```

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["COREAI_API_KEY"],
    base_url="https://inference-api.coreai.uz/v1",
)

completion = client.chat.completions.create(
    model="google/gemma-4-31b-it",
    messages=[{"role": "user", "content": "Salom! Qisqa javob bering."}],
)

print(completion.choices[0].message.content)
```

For streaming:

```python
stream = client.chat.completions.create(
    model="google/gemma-4-31b-it",
    messages=[{"role": "user", "content": "Salom!"}],
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

## JavaScript / TypeScript

```bash
npm install openai
export COREAI_API_KEY="cai_..."
```

```ts
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.COREAI_API_KEY,
  baseURL: "https://inference-api.coreai.uz/v1",
});

const completion = await client.chat.completions.create({
  model: "google/gemma-4-31b-it",
  messages: [{ role: "user", content: "Salom! Qisqa javob bering." }],
});

console.log(completion.choices[0].message.content);
```

## cURL

```bash
curl https://inference-api.coreai.uz/v1/chat/completions \
  -H "Authorization: Bearer $COREAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-4-31b-it",
    "messages": [{"role": "user", "content": "Salom!"}]
  }'
```

List the model IDs enabled for your account:

```bash
curl https://inference-api.coreai.uz/v1/models \
  -H "Authorization: Bearer $COREAI_API_KEY"
```

## Reasoning effort

Qwen3.8 27B supports `none`, `low`, `medium`, and `xhigh`. The default is `low`.

```bash
curl https://inference-api.coreai.uz/v1/chat/completions \
  -H "Authorization: Bearer $COREAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.8-27b",
    "messages": [{"role": "user", "content": "Compare two deployment plans."}],
    "reasoning_effort": "medium"
  }'
```

Read `choices[0].message.reasoning` in a JSON response. In a stream, reasoning arrives under
`choices[0].delta.reasoning` and the final answer arrives under `choices[0].delta.content`.

The object form is also accepted:

```json
{"reasoning": {"enabled": true, "effort": "low"}}
```

## Tool calling

`qwen3.8-27b` accepts function definitions through `tools`. The model returns a structured call;
your application runs the function and sends its result back in a `tool` message.

```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}]

messages = [{"role": "user", "content": "What is the weather in Tashkent?"}]
completion = client.chat.completions.create(
    model="qwen3.8-27b",
    messages=messages,
    tools=tools,
    tool_choice="auto",
)

assistant = completion.choices[0].message
messages.append(assistant)

for call in assistant.tool_calls or []:
    result = '{"temperature_c": 18}'  # Run call.function.name in your application.
    messages.append({
        "role": "tool",
        "tool_call_id": call.id,
        "content": result,
    })

final = client.chat.completions.create(
    model="qwen3.8-27b",
    messages=messages,
    tools=tools,
)
print(final.choices[0].message.content)
```

`tool_choice` accepts `none`, `auto`, `required`, or a named function. Set
`parallel_tool_calls` to control whether the model may return multiple calls. In a stream, call
fragments arrive in `choices[0].delta.tool_calls`; concatenate `function.arguments` fragments in
order before parsing the JSON.

## Current compatibility boundary

The API supports text Chat Completions, streaming, reasoning controls, function tools, common
sampling controls, stop sequences, seeds, and usage reporting. Structured output, images, log
probabilities, multiple choices, and unknown request fields are rejected. See the
[v1 contract](openai-compatible-api-v1.md) for the exact field list and error behavior.

Keep the `x-request-id` response header when reporting a problem. You may also send your own short,
printable `X-Client-Request-Id` for correlation.

## Compatibility smoke tests

Reusable real-server checks using the official OpenAI Python and JavaScript SDKs live in
[`compatibility/`](../compatibility/README.md). They exercise model listing, JSON completion,
streaming chunks, terminal usage, and SDK deserialization. Run them with a disposable CoreAI key
against local development, staging, or production and revoke the key afterward.

## Gemma thinking

Thinking is off by default. Enable it for an individual request:

```python
completion = client.chat.completions.create(
    model="google/gemma-4-31b-it",
    messages=[{"role": "user", "content": "Solve 3x + 7 = 22."}],
    max_completion_tokens=1024,
    extra_body={"reasoning": {"enabled": True}},
)
print(completion.choices[0].message.content)
print(completion.choices[0].message.reasoning)
```

Streaming responses provide `delta.reasoning` and `delta.content` separately.
Use `{"reasoning": {"enabled": true, "exclude": true}}` to omit reasoning text from responses.
Gemma supports thinking on/off; effort levels and separate reasoning-token budgets are unsupported.
