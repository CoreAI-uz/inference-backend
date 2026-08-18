# CoreAI API quickstart

Documentation and account management are available at:

- Product docs: `https://chat.coreai.uz/docs`
- Keys and usage: `https://chat.coreai.uz/console`

CoreAI implements the OpenAI Chat Completions shape. Existing applications normally need only two
configuration changes:

```text
base URL: https://api.coreai.uz/v1
API key:  cai_...
```

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
    "https://api.coreai.uz/v1/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['COREAI_API_KEY']}"},
    json={
        "model": "coreai-model-id",
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
    base_url="https://api.coreai.uz/v1",
)

completion = client.chat.completions.create(
    model="coreai-model-id",
    messages=[{"role": "user", "content": "Salom! Qisqa javob bering."}],
)

print(completion.choices[0].message.content)
```

For streaming:

```python
stream = client.chat.completions.create(
    model="coreai-model-id",
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
  baseURL: "https://api.coreai.uz/v1",
});

const completion = await client.chat.completions.create({
  model: "coreai-model-id",
  messages: [{ role: "user", content: "Salom! Qisqa javob bering." }],
});

console.log(completion.choices[0].message.content);
```

## cURL

```bash
curl https://api.coreai.uz/v1/chat/completions \
  -H "Authorization: Bearer $COREAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "coreai-model-id",
    "messages": [{"role": "user", "content": "Salom!"}]
  }'
```

List the model IDs enabled for your account:

```bash
curl https://api.coreai.uz/v1/models \
  -H "Authorization: Bearer $COREAI_API_KEY"
```

## Current compatibility boundary

The first release supports text Chat Completions, including streaming, common sampling controls,
stop sequences, seeds, and usage reporting. It intentionally rejects tools, structured output,
images, log probabilities, multiple choices, and unknown request fields instead of silently
ignoring them. See the [v1 contract](openai-compatible-api-v1.md) for the exact field list and error
behavior.

Keep the `x-request-id` response header when reporting a problem. You may also send your own short,
printable `X-Client-Request-Id` for correlation.

## Compatibility smoke tests

Reusable real-server checks using the official OpenAI Python and JavaScript SDKs live in
[`compatibility/`](../compatibility/README.md). They exercise model listing, JSON completion,
streaming chunks, terminal usage, and SDK deserialization. Run them with a disposable CoreAI key
against local development, staging, or production and revoke the key afterward.
