# Official OpenAI SDK smoke tests

These clients exercise CoreAI through the public `/v1` boundary with the official Python and
JavaScript SDKs. They test model listing, non-streaming Chat Completions, streaming chunks, and the
terminal streaming usage chunk against a running deployment.

The Docker-based Make targets use the backend image for Python and the repository's pinned Node
image for JavaScript. Build the updated backend image once:

```bash
docker compose build backend
```

Set a disposable CoreAI API key and choose an enabled model:

```bash
export COREAI_BASE_URL="http://localhost:8008/v1"
export COREAI_API_KEY="cai_..."
export COREAI_MODEL="gemma4-31b-it"
```

Run both SDKs:

```bash
make compat-python
make compat-node
```

Use the same commands for staging or production by changing only `COREAI_BASE_URL`,
`COREAI_API_KEY`, and `COREAI_MODEL`. Revoke the disposable key after the run.
