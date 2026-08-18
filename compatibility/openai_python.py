"""Real-server compatibility smoke test using the official OpenAI Python SDK."""

from __future__ import annotations

import json
import os
import sys

from openai import OpenAI


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"error: {name} is required")
    return value


def main() -> None:
    base_url = os.environ.get("COREAI_BASE_URL", "http://localhost:8008/v1").rstrip("/")
    model = required("COREAI_MODEL")
    client = OpenAI(
        api_key=required("COREAI_API_KEY"),
        base_url=base_url,
        max_retries=0,
        timeout=45.0,
    )

    models = client.models.list()
    model_ids = [item.id for item in models.data]
    if model not in model_ids:
        raise SystemExit(f"error: {model!r} not present in /models: {model_ids}")

    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: PYTHON SDK OK"}],
        temperature=0,
        max_tokens=32,
    )
    content = completion.choices[0].message.content or ""
    if not content.strip():
        raise SystemExit("error: non-streaming completion returned empty content")
    if completion.usage is None or completion.usage.total_tokens <= 0:
        raise SystemExit("error: non-streaming completion returned no usage")

    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: PYTHON STREAM OK"}],
        temperature=0,
        max_tokens=32,
        stream=True,
        stream_options={"include_usage": True},
    )
    pieces: list[str] = []
    stream_usage = None
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            pieces.append(chunk.choices[0].delta.content)
        if chunk.usage is not None:
            stream_usage = chunk.usage
    if not "".join(pieces).strip():
        raise SystemExit("error: streaming completion returned empty content")
    if stream_usage is None or stream_usage.total_tokens <= 0:
        raise SystemExit("error: streaming completion returned no terminal usage")

    print(
        json.dumps(
            {
                "sdk": "python",
                "status": "ok",
                "base_url": base_url,
                "model": model,
                "models": model_ids,
                "nonstream_tokens": completion.usage.total_tokens,
                "stream_tokens": stream_usage.total_tokens,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - smoke script must fail with a concise diagnosis
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
