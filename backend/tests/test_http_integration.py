"""HTTP integration coverage for auth, ownership, limits, and SSE durability.

These tests use the development Postgres database, an in-process mock vLLM, and a
small deterministic Redis test double. Run them in the backend container.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from openai import AsyncOpenAI
from sqlalchemy import delete, select, update

from app.auth import google as google_service
from app.auth.google import GoogleClaims
from app.core.config import ModelConfig, get_settings
from app.core.security import encode_access
from app.db.session import SessionLocal, engine
from app.db.types import UsageType
from app.main import create_app
from app.models import (
    ApiContentRecord,
    ApiKey,
    AuthIdentity,
    ConsentEvent,
    Conversation,
    Message,
    UsageEvent,
    User,
    UserProfile,
)
from app.services.data_policy import FREE_DATA_POLICY, LEGAL_ACCEPTANCE_SCOPE
from app.workers.sweep import sweep_api_content
from tests.mock_vllm import MOCK_REASONING
from tests.mock_vllm import app as mock_vllm_app


class FakeRedis:
    """Enough Redis token-bucket behavior for deterministic HTTP tests."""

    def __init__(self) -> None:
        self.buckets: dict[str, tuple[float, float]] = {}

    async def ping(self) -> bool:
        return True

    async def eval(self, _script, _numkeys, key, capacity, refill, cost):
        now = time.monotonic()
        capacity = float(capacity)
        refill = float(refill)
        cost = float(cost)
        tokens, updated_at = self.buckets.get(key, (capacity, now))
        tokens = min(capacity, tokens + max(0, now - updated_at) * refill)
        allowed = int(tokens >= cost)
        retry_after = 0.0
        if allowed:
            tokens -= cost
        elif refill > 0:
            retry_after = (cost - tokens) / refill
        self.buckets[key] = (tokens, now)
        return [allowed, str(tokens), str(retry_after)]


class FakeMinio:
    def bucket_exists(self, _bucket: str) -> bool:
        return True


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests():
    yield
    await engine.dispose()


@pytest.fixture
async def http_client(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "models_config",
        {
            "gemma-mock": ModelConfig(
                endpoint="http://mock-vllm/v1",
                served_model_name="gemma-mock",
                max_context=8192,
                display_name="Gemma (mock)",
            )
        },
    )
    monkeypatch.setattr(settings, "default_model_id", "gemma-mock")
    monkeypatch.setattr(settings, "auto_title", False)
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "allowed_hosts", "*")
    monkeypatch.setattr(settings, "google_client_id", "test-google-client.apps.googleusercontent.com")

    app = create_app()
    app.state.redis = FakeRedis()
    app.state.minio = FakeMinio()
    upstream = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_vllm_app),
        base_url="http://mock-vllm",
    )
    app.state.http = upstream
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, app
    await upstream.aclose()


async def _register(client: httpx.AsyncClient, *, suffix: str | None = None) -> dict:
    suffix = suffix or uuid.uuid4().hex
    response = await client.post(
        "/api/auth/register",
        json={
            "display_name": "Codex Tester",
            "email": f"codex-test-{suffix}@example.com",
            "password": "correct horse battery",
            "legal_terms_accepted": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _cleanup(*, user_ids=(), session_ids=()) -> None:
    async with SessionLocal() as db:
        if user_ids:
            await db.execute(delete(UsageEvent).where(UsageEvent.user_id.in_(user_ids)))
            await db.execute(delete(User).where(User.id.in_(user_ids)))
        if session_ids:
            await db.execute(delete(UsageEvent).where(UsageEvent.session_id.in_(session_ids)))
            await db.execute(delete(Conversation).where(Conversation.session_id.in_(session_ids)))
        await db.commit()


async def test_browser_session_cookies_are_host_only(http_client):
    client, _app = http_client

    anonymous = await client.get("/api/auth/me")
    anonymous_cookie = anonymous.headers.get("set-cookie", "")
    assert "coreai_sid=" in anonymous_cookie
    assert "domain=" not in anonymous_cookie.lower()

    registered = await client.post(
        "/api/auth/register",
        json={
            "display_name": "Cookie Tester",
            "email": f"cookie-{uuid.uuid4().hex}@example.com",
            "password": "correct horse battery staple",
            "legal_terms_accepted": True,
        },
    )
    assert registered.status_code == 201, registered.text
    user_id = uuid.UUID(registered.json()["user"]["id"])
    try:
        auth_cookie = registered.headers.get("set-cookie", "")
        assert "coreai_auth=" in auth_cookie
        assert "domain=" not in auth_cookie.lower()

        logged_out = await client.post("/api/auth/logout")
        clear_cookie = logged_out.headers.get("set-cookie", "")
        assert "coreai_auth=" in clear_cookie
        assert "domain=" not in clear_cookie.lower()
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_registration_requires_and_records_legal_acceptance(http_client):
    client, _app = http_client
    email = f"consent-{uuid.uuid4().hex}@example.com"

    missing = await client.post(
        "/api/auth/register",
        json={
            "display_name": "Consent Tester",
            "email": email,
            "password": "correct horse battery",
        },
    )
    assert missing.status_code == 422

    declined = await client.post(
        "/api/auth/register",
        json={
            "display_name": "Consent Tester",
            "email": email,
            "password": "correct horse battery",
            "legal_terms_accepted": False,
        },
    )
    assert declined.status_code == 422

    accepted = await client.post(
        "/api/auth/register",
        json={
            "display_name": "  Consent   Tester  ",
            "email": email,
            "password": "correct horse battery",
            "locale": "en",
            "legal_terms_accepted": True,
        },
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["legal_terms_accepted"] is True
    assert accepted.json()["user"]["display_name"] == "Consent Tester"
    assert accepted.json()["user"]["onboarding_status"] == "not_started"
    user_id = uuid.UUID(accepted.json()["user"]["id"])
    try:
        async with SessionLocal() as db:
            event = (
                await db.execute(
                    select(ConsentEvent).where(ConsentEvent.user_id == user_id)
                )
            ).scalar_one()
        assert event.scope == LEGAL_ACCEPTANCE_SCOPE
        assert event.action == "grant"
        assert event.source == "registration"
        assert event.locale == "en"
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_progressive_onboarding_can_be_completed_and_updated(http_client):
    client, _app = http_client
    registered = await _register(client)
    user_id = uuid.UUID(registered["user"]["id"])
    try:
        empty = await client.get("/api/auth/profile")
        assert empty.status_code == 200
        assert empty.json() == {
            "display_name": "Codex Tester",
            "role": None,
            "intended_uses": [],
            "organization_name": None,
            "onboarding_status": "not_started",
            "onboarding_version": 1,
            "completed_at": None,
            "skipped_at": None,
        }

        duplicate_uses = await client.post(
            "/api/auth/onboarding",
            json={
                "role": "software_developer",
                "intended_uses": ["programming", "programming"],
            },
        )
        assert duplicate_uses.status_code == 422

        completed = await client.post(
            "/api/auth/onboarding",
            json={
                "role": "software_developer",
                "intended_uses": ["programming", "api_application"],
                "organization_name": "  CoreAI   Labs  ",
            },
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["role"] == "software_developer"
        assert completed.json()["intended_uses"] == ["programming", "api_application"]
        assert completed.json()["organization_name"] == "CoreAI Labs"
        assert completed.json()["onboarding_status"] == "completed"
        assert completed.json()["completed_at"] is not None

        updated = await client.patch(
            "/api/auth/profile",
            json={"display_name": "  Sanjar   B.  ", "organization_name": None},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["display_name"] == "Sanjar B."
        assert updated.json()["organization_name"] is None

        cleared_name = await client.patch(
            "/api/auth/profile", json={"display_name": None}
        )
        assert cleared_name.status_code == 422

        current = await client.get("/api/auth/me")
        assert current.json()["user"]["display_name"] == "Sanjar B."
        assert current.json()["user"]["onboarding_status"] == "completed"
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_progressive_onboarding_can_be_skipped(http_client):
    client, _app = http_client
    registered = await _register(client)
    user_id = uuid.UUID(registered["user"]["id"])
    try:
        skipped = await client.post("/api/auth/onboarding/skip")
        assert skipped.status_code == 200, skipped.text
        assert skipped.json()["onboarding_status"] == "skipped"
        assert skipped.json()["skipped_at"] is not None

        repeated = await client.post("/api/auth/onboarding/skip")
        assert repeated.status_code == 200
        assert repeated.json()["skipped_at"] == skipped.json()["skipped_at"]

        async with SessionLocal() as db:
            profile = await db.get(UserProfile, user_id)
        assert profile is not None
        assert profile.completed_at is None
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_new_and_returning_google_auth_flow(http_client, monkeypatch):
    client, _app = http_client
    suffix = uuid.uuid4().hex
    email = f"google-{suffix}@example.com"
    subject = f"google-subject-{suffix}"

    async def verify(_credential: str) -> GoogleClaims:
        return GoogleClaims(
            subject=subject,
            email=email,
            display_name="Google Tester",
        )

    monkeypatch.setattr(google_service, "verify_google_credential", verify)

    providers = await client.get("/api/auth/providers")
    assert providers.status_code == 200
    assert providers.json()["google"] == {
        "enabled": True,
        "client_id": "test-google-client.apps.googleusercontent.com",
    }

    started = await client.post(
        "/api/auth/google", json={"credential": "g" * 200}
    )
    assert started.status_code == 200, started.text
    assert started.json() == {
        "status": "registration_required",
        "me": None,
        "email": email,
        "display_name": "Google Tester",
    }
    pending_cookie = started.headers.get("set-cookie", "")
    assert "coreai_google_pending=" in pending_cookie
    assert "HttpOnly" in pending_cookie
    assert "Path=/api/auth/google" in pending_cookie

    pending = await client.get("/api/auth/google/pending")
    assert pending.status_code == 200
    assert pending.json() == {"email": email, "display_name": "Google Tester"}

    declined = await client.post(
        "/api/auth/google/complete-registration",
        json={
            "display_name": "Google Tester",
            "locale": "en",
            "legal_terms_accepted": False,
        },
    )
    assert declined.status_code == 422

    completed = await client.post(
        "/api/auth/google/complete-registration",
        json={
            "display_name": "  Google   Tester  ",
            "locale": "en",
            "legal_terms_accepted": True,
        },
    )
    assert completed.status_code == 201, completed.text
    assert completed.json()["user"]["display_name"] == "Google Tester"
    assert completed.json()["user"]["email_verified"] is True
    user_id = uuid.UUID(completed.json()["user"]["id"])
    try:
        assert "coreai_google_pending=\"\"" in completed.headers.get("set-cookie", "")
        async with SessionLocal() as db:
            user = await db.get(User, user_id)
            identity = (
                await db.execute(
                    select(AuthIdentity).where(AuthIdentity.user_id == user_id)
                )
            ).scalar_one()
            consent = (
                await db.execute(
                    select(ConsentEvent).where(ConsentEvent.user_id == user_id)
                )
            ).scalar_one()
        assert user is not None and user.password_hash is None
        assert identity.provider == "google"
        assert identity.provider_subject == subject
        assert consent.source == "google_registration"

        methods = await client.get("/api/auth/identities")
        assert methods.status_code == 200
        assert methods.json()["password_enabled"] is False
        assert methods.json()["identities"][0]["provider"] == "google"

        last_method = await client.delete("/api/auth/identities/google")
        assert last_method.status_code == 409
        assert last_method.json()["error"] == "last_sign_in_method"

        await client.post("/api/auth/logout")
        returning = await client.post(
            "/api/auth/google", json={"credential": "g" * 200}
        )
        assert returning.status_code == 200, returning.text
        assert returning.json()["status"] == "authenticated"
        assert returning.json()["me"]["user"]["id"] == str(user_id)
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_google_auth_does_not_merge_by_matching_email(http_client, monkeypatch):
    client, _app = http_client
    registered = await _register(client)
    user_id = uuid.UUID(registered["user"]["id"])
    email = registered["user"]["email"]

    async def verify(_credential: str) -> GoogleClaims:
        return GoogleClaims(
            subject=f"unlinked-{uuid.uuid4().hex}",
            email=email,
            display_name="Existing User",
        )

    monkeypatch.setattr(google_service, "verify_google_credential", verify)
    try:
        await client.post("/api/auth/logout")
        collision = await client.post(
            "/api/auth/google", json={"credential": "g" * 200}
        )
        assert collision.status_code == 409
        assert collision.json()["error"] == "account_link_required"
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_google_completion_requires_valid_pending_cookie(http_client):
    client, _app = http_client
    response = await client.post(
        "/api/auth/google/complete-registration",
        json={
            "display_name": "No Pending Session",
            "locale": "en",
            "legal_terms_accepted": True,
        },
    )
    assert response.status_code == 401
    assert response.json()["error"] == "pending_registration_expired"


async def test_password_user_can_link_and_unlink_google(http_client, monkeypatch):
    client, _app = http_client
    registered = await _register(client)
    user_id = uuid.UUID(registered["user"]["id"])
    linked_email = f"linked-{uuid.uuid4().hex}@example.com"

    async def verify(_credential: str) -> GoogleClaims:
        return GoogleClaims(
            subject=f"linked-subject-{uuid.uuid4().hex}",
            email=linked_email,
            display_name="Linked Identity",
        )

    monkeypatch.setattr(google_service, "verify_google_credential", verify)
    try:
        initial = await client.get("/api/auth/identities")
        assert initial.status_code == 200
        assert initial.json() == {"password_enabled": True, "identities": []}

        linked = await client.post(
            "/api/auth/identities/google", json={"credential": "g" * 200}
        )
        assert linked.status_code == 200, linked.text
        assert linked.json() == {"provider": "google", "email": linked_email}

        methods = await client.get("/api/auth/identities")
        assert methods.json()["password_enabled"] is True
        assert methods.json()["identities"][0]["email"] == linked_email

        removed = await client.delete("/api/auth/identities/google")
        assert removed.status_code == 204
        after = await client.get("/api/auth/identities")
        assert after.json()["identities"] == []
    finally:
        await _cleanup(user_ids=(user_id,))


def _sse_payload(body: str, event: str) -> dict:
    marker = f"event: {event}\n"
    frame = next(part for part in body.split("\n\n") if part.startswith(marker))
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


def _sse_payloads(body: str, event: str) -> list[dict]:
    marker = f"event: {event}\n"
    payloads = []
    for frame in body.split("\n\n"):
        if not frame.startswith(marker):
            continue
        data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
        payloads.append(json.loads(data_line.removeprefix("data: ")))
    return payloads


async def test_registration_login_and_conversation_ownership(http_client):
    owner, app = http_client
    me = await _register(owner)
    owner_id = uuid.UUID(me["user"]["id"])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as outsider:
        outsider_me = await _register(outsider)
        outsider_id = uuid.UUID(outsider_me["user"]["id"])
        try:
            created = await owner.post("/api/conversations", json={"title": "private"})
            assert created.status_code == 201
            conversation_id = created.json()["id"]
            hidden = await outsider.get(f"/api/conversations/{conversation_id}")
            assert hidden.status_code == 404

            await owner.post("/api/auth/logout")
            logged_in = await owner.post(
                "/api/auth/login",
                json={"email": me["user"]["email"], "password": "correct horse battery"},
            )
            assert logged_in.status_code == 200
            assert logged_in.json()["user"]["id"] == str(owner_id)
        finally:
            await _cleanup(user_ids=(owner_id, outsider_id))


async def test_stale_jwt_does_not_grant_authenticated_access(http_client):
    client, _app = http_client
    client.cookies.set("coreai_auth", encode_access(uuid.uuid4()))
    response = await client.get("/api/conversations")
    assert response.status_code == 401


async def test_health_checks_require_a_real_completion(http_client):
    client, app = http_client

    liveness = await client.get("/api/health")
    assert liveness.status_code == 200
    assert liveness.json() == {"status": "ok"}
    assert "set-cookie" not in liveness.headers

    healthy = await client.get("/api/health/ready")
    assert healthy.status_code == 200, healthy.text
    healthy_payload = healthy.json()
    assert healthy_payload["status"] == "ready"
    assert healthy_payload["checks"] == {
        "postgres": "ok",
        "redis": "ok",
        "minio": "ok",
        "inference": "ready",
    }
    assert healthy_payload["models"] == {"gemma-mock": "ok"}
    assert healthy_payload["inference_cached"] is False
    assert "set-cookie" not in healthy.headers

    requests: list[httpx.Request] = []

    async def unavailable_worker(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, json={"error": {"message": "worker unavailable"}})

    original_http = app.state.http
    failing_http = httpx.AsyncClient(
        transport=httpx.MockTransport(unavailable_worker),
        base_url="http://mock-vllm",
    )
    app.state.http = failing_http
    try:
        cached_ready = await client.get("/api/health/ready")
        assert cached_ready.status_code == 200
        assert cached_ready.json()["status"] == "ready"
        assert cached_ready.json()["inference_cached"] is True
        assert requests == []

        inference = await client.get("/api/health/inference")
        assert inference.status_code == 503
        assert inference.json()["status"] == "unavailable"
        assert inference.json()["models"] == {"gemma-mock": "http 503"}
        assert inference.json()["cached"] is False

        unavailable = await client.get("/api/health/ready")
        assert unavailable.status_code == 503
        assert unavailable.json()["status"] == "unavailable"
        assert unavailable.json()["checks"]["inference"] == "unavailable"
        assert unavailable.json()["inference_cached"] is True
        assert len(requests) == 1
        assert all(request.method == "POST" for request in requests)
        assert all(request.url.path.endswith("/chat/completions") for request in requests)
    finally:
        app.state.http = original_http
        await failing_http.aclose()


async def test_minio_is_non_blocking_while_ocr_is_deferred(http_client):
    client, app = http_client

    class MissingMinio:
        def bucket_exists(self, _bucket: str) -> bool:
            return False

    app.state.minio = MissingMinio()
    response = await client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["minio"] == "missing-bucket"


async def test_login_attempts_are_throttled(http_client, monkeypatch):
    client, _app = http_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rl_login_per_ip", 2)
    monkeypatch.setattr(settings, "rl_login_per_account", 2)
    payload = {"email": f"missing-{uuid.uuid4().hex}@example.com", "password": "wrong"}

    assert (await client.post("/api/auth/login", json=payload)).status_code == 401
    assert (await client.post("/api/auth/login", json=payload)).status_code == 401
    limited = await client.post("/api/auth/login", json=payload)
    assert limited.status_code == 429
    assert limited.json()["error"] == "rate_limited"
    assert int(limited.headers["retry-after"]) > 0


async def test_sse_persists_reply_and_live_limit_is_not_lifetime_usage(http_client, monkeypatch):
    client, _app = http_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rl_anon_chat", 1)
    me_before = (await client.get("/api/auth/me")).json()
    session_id = me_before["session_id"]
    assert me_before["limits"]["chat_remaining"] == 1

    try:
        response = await client.post(
            "/api/chat/completions",
            json={"model": "gemma-mock", "user_content": "persist this reply"},
        )
        assert response.status_code == 200
        done = _sse_payload(response.text, "done")
        conversation_id = uuid.UUID(done["conversation_id"])
        message_id = uuid.UUID(done["message_id"])

        async with SessionLocal() as db:
            messages = list(
                (
                    await db.execute(
                        select(Message).where(Message.conversation_id == conversation_id)
                    )
                )
                .scalars()
                .all()
            )
            usage = (
                await db.execute(select(UsageEvent).where(UsageEvent.message_id == message_id))
            ).scalar_one()
        assert len(messages) == 2
        assert usage.output_tokens > 0

        me_after = (await client.get("/api/auth/me")).json()
        assert me_after["usage"]["chat_messages"] == 1
        assert me_after["limits"]["chat_remaining"] == 0
        limited = await client.post(
            "/api/chat/completions",
            json={"model": "gemma-mock", "user_content": "one too many"},
        )
        assert limited.status_code == 429
    finally:
        await _cleanup(session_ids=(session_id,))


async def test_sse_streams_and_persists_structured_reasoning(http_client, monkeypatch):
    client, _app = http_client
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "models_config",
        {
            "qwen3.8-mock": ModelConfig(
                endpoint="http://mock-vllm/v1",
                served_model_name="gemma-mock",
                max_context=262_144,
                display_name="Qwen3.8 (mock)",
                supports_thinking=True,
                supports_tools=True,
            )
        },
    )
    me = (await client.get("/api/auth/me")).json()
    session_id = me["session_id"]

    try:
        response = await client.post(
            "/api/chat/completions",
            json={
                "model": "qwen3.8-mock",
                "user_content": "exercise structured reasoning",
                "reasoning_effort": "medium",
            },
        )
        assert response.status_code == 200, response.text

        reasoning = "".join(
            payload["content"] for payload in _sse_payloads(response.text, "reasoning")
        )
        answer = "".join(payload["content"] for payload in _sse_payloads(response.text, "delta"))
        done = _sse_payload(response.text, "done")
        assert reasoning == MOCK_REASONING
        assert answer.startswith("Hello! This is a mock streaming response")

        async with SessionLocal() as db:
            assistant = await db.get(Message, uuid.UUID(done["message_id"]))
            usage = (
                await db.execute(
                    select(UsageEvent).where(
                        UsageEvent.message_id == uuid.UUID(done["message_id"])
                    )
                )
            ).scalar_one()
        assert assistant is not None
        assert assistant.reasoning == MOCK_REASONING
        assert assistant.content == answer
        assert assistant.reasoning_ms is not None
        assert usage.reasoning_tokens > 0
    finally:
        await _cleanup(session_ids=(session_id,))


async def test_reasoning_efforts_and_response_normalization(http_client, monkeypatch):
    client, app = http_client
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "models_config",
        {
            "qwen3.8-mock": ModelConfig(
                endpoint="http://mock-vllm/v1",
                served_model_name="qwen3.8-mock",
                max_context=262_144,
                display_name="Qwen3.8 (mock)",
                supports_thinking=True,
            ),
            "gemma-mock": ModelConfig(
                endpoint="http://mock-vllm/v1",
                served_model_name="gemma-mock",
                max_context=16_384,
                display_name="Gemma (mock)",
            ),
        },
    )
    monkeypatch.setattr(settings, "default_model_id", "qwen3.8-mock")

    me = await _register(client)
    user_id = uuid.UUID(me["user"]["id"])
    created_key = await client.post("/api/developer/keys", json={"name": "Reasoning"})
    credential = created_key.json()["key"]
    headers = {"Authorization": f"Bearer {credential}"}

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as sdk:
            models = (await sdk.get("/v1/models", headers=headers)).json()["data"]
            qwen = next(model for model in models if model["id"] == "qwen3.8-mock")
            assert qwen["capabilities"]["reasoning"] == {
                "supported": True,
                "efforts": ["none", "low", "medium", "xhigh"],
                "default_effort": "xhigh",
            }

            nonstream = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "qwen3.8-mock",
                    "messages": [{"role": "user", "content": "reason carefully"}],
                    "reasoning_effort": "medium",
                },
            )
            assert nonstream.status_code == 200, nonstream.text
            message = nonstream.json()["choices"][0]["message"]
            assert message["reasoning"] == MOCK_REASONING
            assert "reasoning_content" not in message
            assert (
                nonstream.json()["usage"]["completion_tokens_details"]["reasoning_tokens"]
                > 0
            )

            streamed = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "qwen3.8-mock",
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "Earlier answer",
                            "reasoning_content": "Earlier reasoning",
                        },
                        {"role": "user", "content": "continue"},
                    ],
                    "reasoning": {"enabled": True, "effort": "low"},
                    "stream": True,
                },
            )
            assert streamed.status_code == 200, streamed.text
            chunks = [
                json.loads(line.removeprefix("data: "))
                for line in streamed.text.splitlines()
                if line.startswith("data: {")
            ]
            deltas = [choice["delta"] for chunk in chunks for choice in chunk["choices"]]
            assert "".join(delta.get("reasoning", "") for delta in deltas) == MOCK_REASONING
            assert all("reasoning_content" not in delta for delta in deltas)

            disabled = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "qwen3.8-mock",
                    "messages": [{"role": "user", "content": "answer directly"}],
                    "reasoning": {"enabled": False},
                },
            )
            assert disabled.status_code == 200
            assert "reasoning" not in disabled.json()["choices"][0]["message"]

            unsupported = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gemma-mock",
                    "messages": [{"role": "user", "content": "reason"}],
                    "reasoning_effort": "low",
                },
            )
            assert unsupported.status_code == 400
            assert unsupported.json()["error"]["param"] == "reasoning_effort"
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_tool_calling_nonstream_stream_and_followup(http_client, monkeypatch):
    client, app = http_client
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "models_config",
        {
            "qwen3.8-mock": ModelConfig(
                endpoint="http://mock-vllm/v1",
                served_model_name="qwen3.8-mock",
                max_context=262_144,
                display_name="Qwen3.8 (mock)",
                supports_thinking=True,
                supports_tools=True,
            ),
            "gemma-mock": ModelConfig(
                endpoint="http://mock-vllm/v1",
                served_model_name="gemma-mock",
                max_context=16_384,
                display_name="Gemma (mock)",
            ),
        },
    )
    me = await _register(client)
    user_id = uuid.UUID(me["user"]["id"])
    created_key = await client.post("/api/developer/keys", json={"name": "Tools"})
    credential = created_key.json()["key"]
    headers = {"Authorization": f"Bearer {credential}"}
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a city.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }
    ]

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as sdk:
            models = (await sdk.get("/v1/models", headers=headers)).json()["data"]
            qwen = next(model for model in models if model["id"] == "qwen3.8-mock")
            assert qwen["capabilities"]["tools"] == {
                "supported": True,
                "tool_choice": ["none", "auto", "required"],
                "parallel_tool_calls": True,
            }

            first = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "qwen3.8-mock",
                    "messages": [
                        {"role": "user", "content": "What is the weather in Tashkent?"}
                    ],
                    "tools": tools,
                    "tool_choice": {
                        "type": "function",
                        "function": {"name": "get_weather"},
                    },
                    "parallel_tool_calls": True,
                    "reasoning_effort": "none",
                },
            )
            assert first.status_code == 200, first.text
            first_choice = first.json()["choices"][0]
            assert first_choice["finish_reason"] == "tool_calls"
            assert first_choice["message"]["content"] is None
            tool_call = first_choice["message"]["tool_calls"][0]
            assert tool_call["function"] == {
                "name": "get_weather",
                "arguments": '{"city":"Tashkent"}',
            }

            followup = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "qwen3.8-mock",
                    "messages": [
                        {"role": "user", "content": "What is the weather in Tashkent?"},
                        first_choice["message"],
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": '{"temperature_c":31}',
                        },
                    ],
                    "tools": tools,
                    "tool_choice": "auto",
                    "reasoning_effort": "none",
                },
            )
            assert followup.status_code == 200, followup.text
            assert followup.json()["choices"][0]["finish_reason"] == "stop"
            assert "31" in followup.json()["choices"][0]["message"]["content"]

            streamed = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "qwen3.8-mock",
                    "messages": [
                        {"role": "user", "content": "Call the weather function."}
                    ],
                    "tools": tools,
                    "tool_choice": "required",
                    "reasoning_effort": "none",
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            )
            assert streamed.status_code == 200, streamed.text
            chunks = [
                json.loads(line.removeprefix("data: "))
                for line in streamed.text.splitlines()
                if line.startswith("data: {")
            ]
            deltas = [choice["delta"] for chunk in chunks for choice in chunk["choices"]]
            streamed_calls = [
                call for delta in deltas for call in delta.get("tool_calls", [])
            ]
            assert streamed_calls[0]["function"]["name"] == "get_weather"
            assert "".join(
                call.get("function", {}).get("arguments", "") for call in streamed_calls
            ) == '{"city":"Tashkent"}'
            assert any(
                choice.get("finish_reason") == "tool_calls"
                for chunk in chunks
                for choice in chunk["choices"]
            )
            assert chunks[-1]["usage"]["total_tokens"] > 0

            unsupported = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gemma-mock",
                    "messages": [{"role": "user", "content": "Call a tool."}],
                    "tools": tools,
                },
            )
            assert unsupported.status_code == 400
            assert unsupported.json()["error"]["param"] == "tools"

        async with SessionLocal() as db:
            records = list(
                (
                    await db.execute(
                        select(ApiContentRecord)
                        .where(ApiContentRecord.user_id == user_id)
                        .order_by(ApiContentRecord.created_at)
                    )
                )
                .scalars()
                .all()
            )
        assert any(
            record.response_body.get("choices", [{}])[0]
            .get("message", {})
            .get("tool_calls")
            for record in records
        )
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_anonymous_first_turn_gets_generated_title(http_client, monkeypatch):
    client, _app = http_client
    settings = get_settings()
    monkeypatch.setattr(settings, "auto_title", True)
    me = (await client.get("/api/auth/me")).json()
    session_id = me["session_id"]

    try:
        response = await client.post(
            "/api/chat/completions",
            json={
                "model": "gemma-mock",
                "user_content": "plan a private GPU deployment",
            },
        )
        assert response.status_code == 200

        title_event = _sse_payload(response.text, "title")
        done = _sse_payload(response.text, "done")
        assert title_event["conversation_id"] == done["conversation_id"]
        assert title_event["title"] == "Plan A Private GPU Deployment"
        assert done["title"] == title_event["title"]

        async with SessionLocal() as db:
            conversation = await db.get(Conversation, uuid.UUID(done["conversation_id"]))
            assert conversation is not None
            assert conversation.user_id is None
            assert conversation.session_id == session_id
            assert conversation.title == title_event["title"]
    finally:
        await _cleanup(session_ids=(session_id,))


async def test_metering_failure_cannot_roll_back_streamed_chat(http_client, monkeypatch):
    client, _app = http_client
    me = (await client.get("/api/auth/me")).json()
    session_id = me["session_id"]

    async def fail_metering(*_args, **_kwargs):
        raise RuntimeError("simulated ledger outage")

    monkeypatch.setattr("app.services.chat_service.record_usage", fail_metering)
    try:
        response = await client.post(
            "/api/chat/completions",
            json={"model": "gemma-mock", "user_content": "save despite metering"},
        )
        assert response.status_code == 200
        done = _sse_payload(response.text, "done")
        assert done["conversation_id"] and done["message_id"]

        conversation_id = uuid.UUID(done["conversation_id"])
        message_id = uuid.UUID(done["message_id"])
        async with SessionLocal() as db:
            assert await db.get(Conversation, conversation_id) is not None
            assert await db.get(Message, message_id) is not None
            usage = (
                await db.execute(select(UsageEvent).where(UsageEvent.message_id == message_id))
            ).scalar_one_or_none()
        assert usage is None
    finally:
        await _cleanup(session_ids=(session_id,))


async def test_api_key_lifecycle_and_authenticated_models(http_client):
    client, app = http_client
    unauthorized = await client.get("/v1/models")
    assert unauthorized.status_code == 401
    assert unauthorized.json() == {
        "error": {
            "message": "Incorrect API key provided.",
            "type": "invalid_request_error",
            "param": None,
            "code": "invalid_api_key",
        }
    }

    me = await _register(client)
    user_id = uuid.UUID(me["user"]["id"])
    try:
        created = await client.post("/api/developer/keys", json={"name": "Local SDK"})
        assert created.status_code == 201, created.text
        credential = created.json()["key"]
        key_id = uuid.UUID(created.json()["id"])
        assert credential.startswith(f"{created.json()['prefix']}_")

        listed = await client.get("/api/developer/keys")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == str(key_id)
        assert "key" not in listed.json()[0]

        async with SessionLocal() as db:
            stored = await db.get(ApiKey, key_id)
            assert stored is not None
            assert stored.secret_digest != credential
            assert credential not in stored.secret_digest

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as sdk:
            models = await sdk.get("/v1/models", headers={"Authorization": f"Bearer {credential}"})
            assert models.status_code == 200, models.text
            assert models.json()["object"] == "list"
            assert models.json()["data"][0]["id"] == "gemma-mock"
            assert "coreai_sid" not in models.cookies

            revoked = await client.delete(f"/api/developer/keys/{key_id}")
            assert revoked.status_code == 204
            rejected = await sdk.get(
                "/v1/models", headers={"Authorization": f"Bearer {credential}"}
            )
            assert rejected.status_code == 401
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_existing_account_must_accept_legal_terms_before_api_access(http_client):
    client, app = http_client
    me = await _register(client)
    user_id = uuid.UUID(me["user"]["id"])
    created = await client.post("/api/developer/keys", json={"name": "Existing key"})
    assert created.status_code == 201, created.text
    credential = created.json()["key"]

    try:
        async with SessionLocal() as db:
            await db.execute(delete(ConsentEvent).where(ConsentEvent.user_id == user_id))
            await db.commit()

        current = await client.get("/api/auth/me")
        assert current.status_code == 200
        assert current.json()["legal_terms_accepted"] is False

        blocked_creation = await client.post(
            "/api/developer/keys", json={"name": "Blocked key"}
        )
        assert blocked_creation.status_code == 403
        assert blocked_creation.json()["error"] == "legal_acceptance_required"

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as sdk:
            blocked_request = await sdk.get(
                "/v1/models", headers={"Authorization": f"Bearer {credential}"}
            )
            assert blocked_request.status_code == 403
            assert blocked_request.json()["error"]["code"] == "legal_acceptance_required"

            accepted = await client.post(
                "/api/auth/legal-acceptance", json={"accepted": True}
            )
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["accepted"] is True

            models = await sdk.get(
                "/v1/models", headers={"Authorization": f"Bearer {credential}"}
            )
            assert models.status_code == 200, models.text
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_developer_usage_aggregates_tokens_without_content(http_client):
    client, _app = http_client
    assert (await client.get("/api/developer/usage")).status_code == 401

    me = await _register(client)
    user_id = uuid.UUID(me["user"]["id"])
    try:
        async with SessionLocal() as db:
            db.add_all(
                [
                    UsageEvent(
                        user_id=user_id,
                        type=UsageType.CHAT,
                        source="web",
                        model="gemma-mock",
                        input_tokens=10,
                        output_tokens=4,
                    ),
                    UsageEvent(
                        user_id=user_id,
                        type=UsageType.CHAT,
                        source="api",
                        model="gemma-mock",
                        input_tokens=20,
                        output_tokens=8,
                        cached_input_tokens=6,
                        reasoning_tokens=2,
                    ),
                ]
            )
            await db.commit()

        response = await client.get("/api/developer/usage")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["lifetime"] == {
            "requests": 2,
            "input_tokens": 30,
            "output_tokens": 12,
            "cached_input_tokens": 6,
            "reasoning_tokens": 2,
        }
        assert payload["last_24_hours"] == payload["lifetime"]
        assert {row["source"] for row in payload["by_source"]} == {"api", "web"}
        assert payload["by_model"][0]["model"] == "gemma-mock"
        assert "content" not in response.text
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_openai_chat_nonstream_stream_and_usage(http_client):
    client, app = http_client
    me = await _register(client)
    user_id = uuid.UUID(me["user"]["id"])
    created_key = await client.post("/api/developer/keys", json={"name": "Compatibility"})
    credential = created_key.json()["key"]
    key_id = uuid.UUID(created_key.json()["id"])
    headers = {
        "Authorization": f"Bearer {credential}",
        "X-Client-Request-Id": "sdk-test-123",
    }

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as sdk:
            response = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gemma-mock",
                    "messages": [{"role": "user", "content": "cached nonstream hello"}],
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["object"] == "chat.completion"
            assert body["id"] == "chatcmpl-mock"
            assert body["system_fingerprint"] == "mock-vllm-fingerprint"
            assert body["choices"][0]["message"]["role"] == "assistant"
            assert body["usage"]["total_tokens"] > 0
            assert body["usage"]["prompt_tokens_details"]["cached_tokens"] == 1
            assert response.headers["x-client-request-id"] == "sdk-test-123"
            assert int(response.headers["x-ratelimit-remaining-requests"]) >= 0

            streamed = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gemma-mock",
                    "messages": [{"role": "user", "content": "stream hello"}],
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            )
            assert streamed.status_code == 200, streamed.text
            assert "event: delta" not in streamed.text
            assert "data: [DONE]" in streamed.text
            chunks = [
                json.loads(line.removeprefix("data: "))
                for line in streamed.text.splitlines()
                if line.startswith("data: {")
            ]
            assert chunks[0]["object"] == "chat.completion.chunk"
            assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
            assert chunks[-1]["choices"] == []
            assert chunks[-1]["usage"]["total_tokens"] > 0

            streamed_without_usage = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gemma-mock",
                    "messages": [{"role": "user", "content": "stream without public usage"}],
                    "stream": True,
                },
            )
            assert streamed_without_usage.status_code == 200
            hidden_usage_chunks = [
                json.loads(line.removeprefix("data: "))
                for line in streamed_without_usage.text.splitlines()
                if line.startswith("data: {")
            ]
            assert all("usage" not in chunk for chunk in hidden_usage_chunks)
            assert "data: [DONE]" in streamed_without_usage.text

            invalid = await sdk.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gemma-mock",
                    "messages": [{"role": "user", "content": "hello"}],
                    "tools": [],
                },
            )
            assert invalid.status_code == 400
            assert invalid.json()["error"]["type"] == "invalid_request_error"
            assert invalid.json()["error"]["param"] == "tools"

        async with SessionLocal() as db:
            usage = list(
                (
                    await db.execute(
                        select(UsageEvent).where(
                            UsageEvent.user_id == user_id,
                            UsageEvent.api_key_id == key_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            retained = list(
                (
                    await db.execute(
                        select(ApiContentRecord)
                        .where(ApiContentRecord.user_id == user_id)
                        .order_by(ApiContentRecord.created_at)
                    )
                )
                .scalars()
                .all()
            )
        assert len(usage) == 3
        assert all(
            row.source == "api" and row.data_policy == FREE_DATA_POLICY for row in usage
        )
        assert all(row.message_id is None for row in usage)
        assert sorted(row.cached_input_tokens for row in usage) == [0, 0, 1]
        assert len(retained) == 3
        assert all(row.data_policy == FREE_DATA_POLICY for row in retained)
        assert all(row.expires_at > datetime.now(UTC) + timedelta(days=29) for row in retained)
        assert {row.request_body["messages"][0]["content"] for row in retained} == {
            "cached nonstream hello",
            "stream hello",
            "stream without public usage",
        }
        assert all(row.response_body["choices"][0] for row in retained)

        async with SessionLocal() as db:
            await db.execute(
                update(ApiContentRecord)
                .where(ApiContentRecord.user_id == user_id)
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await db.commit()
        assert await sweep_api_content() == 3
        async with SessionLocal() as db:
            assert await db.scalar(
                select(ApiContentRecord.id).where(ApiContentRecord.user_id == user_id)
            ) is None
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_openai_api_accepts_long_input_for_high_context_models(http_client, monkeypatch):
    client, app = http_client
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "models_config",
        {
            "qwen3.8-27b": ModelConfig(
                endpoint="http://mock-vllm/v1",
                served_model_name="gemma-mock",
                max_context=262_144,
                display_name="Qwen3.8 27B",
            )
        },
    )
    monkeypatch.setattr(settings, "default_model_id", "qwen3.8-27b")

    me = await _register(client)
    user_id = uuid.UUID(me["user"]["id"])
    created_key = await client.post("/api/developer/keys", json={"name": "Long context"})
    credential = created_key.json()["key"]

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as sdk:
            response = await sdk.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {credential}"},
                json={
                    "model": "qwen3.8-27b",
                    "messages": [{"role": "user", "content": "x" * 30_000}],
                },
            )

        assert response.status_code == 200, response.text
        assert response.json()["model"] == "gemma-mock"
    finally:
        await _cleanup(user_ids=(user_id,))


async def test_official_openai_python_sdk_nonstream_stream_and_models(http_client):
    session, app = http_client
    me = await _register(session)
    user_id = uuid.UUID(me["user"]["id"])
    created_key = await session.post("/api/developer/keys", json={"name": "Official Python SDK"})
    credential = created_key.json()["key"]
    key_id = uuid.UUID(created_key.json()["id"])

    sdk_http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    sdk = AsyncOpenAI(
        api_key=credential,
        base_url="http://testserver/v1",
        http_client=sdk_http,
        max_retries=0,
    )
    try:
        models = await sdk.models.list()
        assert [model.id for model in models.data] == ["gemma-mock"]

        completion = await sdk.chat.completions.create(
            model="gemma-mock",
            messages=[{"role": "user", "content": "official sdk nonstream"}],
            max_tokens=64,
            temperature=0,
        )
        assert completion.object == "chat.completion"
        assert completion.choices[0].message.content
        assert completion.usage is not None
        assert completion.usage.total_tokens > 0

        stream = await sdk.chat.completions.create(
            model="gemma-mock",
            messages=[{"role": "user", "content": "official sdk stream"}],
            stream=True,
            stream_options={"include_usage": True},
            max_tokens=64,
        )
        chunks = [chunk async for chunk in stream]
        assert chunks[0].object == "chat.completion.chunk"
        assert "".join(chunk.choices[0].delta.content or "" for chunk in chunks if chunk.choices)
        assert chunks[-1].choices == []
        assert chunks[-1].usage is not None
        assert chunks[-1].usage.total_tokens > 0

        async with SessionLocal() as db:
            usage = list(
                (
                    await db.execute(
                        select(UsageEvent).where(
                            UsageEvent.user_id == user_id,
                            UsageEvent.api_key_id == key_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(usage) == 2
        assert all(row.status_code == 200 for row in usage)
    finally:
        await sdk.close()
        await _cleanup(user_ids=(user_id,))


async def test_openai_sampling_controls_are_forwarded_and_connection_errors_normalized(
    http_client,
):
    session, app = http_client
    me = await _register(session)
    user_id = uuid.UUID(me["user"]["id"])
    created_key = await session.post("/api/developer/keys", json={"name": "Forwarding"})
    credential = created_key.json()["key"]
    headers = {"Authorization": f"Bearer {credential}"}
    captured: dict = {}

    async def capture(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-forwarded",
                "object": "chat.completion",
                "created": 1,
                "model": "gemma-mock",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "forwarded"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    original_http = app.state.http
    capture_http = httpx.AsyncClient(transport=httpx.MockTransport(capture))
    app.state.http = capture_http
    try:
        response = await session.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "gemma-mock",
                "messages": [{"role": "user", "content": "forward these controls"}],
                "temperature": 0.4,
                "top_p": 0.8,
                "max_tokens": 77,
                "stop": ["END", "STOP"],
                "seed": 42,
                "frequency_penalty": 0.2,
                "presence_penalty": -0.1,
                "user": "compat-user",
            },
        )
        assert response.status_code == 200, response.text
        assert {
            key: captured[key]
            for key in (
                "temperature",
                "top_p",
                "max_tokens",
                "stop",
                "seed",
                "frequency_penalty",
                "presence_penalty",
                "user",
            )
        } == {
            "temperature": 0.4,
            "top_p": 0.8,
            "max_tokens": 77,
            "stop": ["END", "STOP"],
            "seed": 42,
            "frequency_penalty": 0.2,
            "presence_penalty": -0.1,
            "user": "compat-user",
        }
        assert response.headers["x-request-id"]
    finally:
        app.state.http = original_http
        await capture_http.aclose()

    async def connection_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("worker offline", request=request)

    failing_http = httpx.AsyncClient(transport=httpx.MockTransport(connection_failure))
    app.state.http = failing_http
    try:
        unavailable = await session.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "gemma-mock",
                "messages": [{"role": "user", "content": "unavailable"}],
            },
        )
        assert unavailable.status_code == 503
        assert unavailable.headers["retry-after"] == "2"
        assert unavailable.headers["x-request-id"]
        assert unavailable.json() == {
            "error": {
                "message": "The model is temporarily unavailable. Please retry shortly.",
                "type": "server_error",
                "param": None,
                "code": "service_unavailable",
            }
        }
    finally:
        app.state.http = original_http
        await failing_http.aclose()
        await _cleanup(user_ids=(user_id,))


async def test_web_and_api_share_the_registered_request_bucket(http_client, monkeypatch):
    client, app = http_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rl_user_chat", 1)
    me = await _register(client)
    user_id = uuid.UUID(me["user"]["id"])
    created_key = await client.post("/api/developer/keys", json={"name": "Shared limit"})
    credential = created_key.json()["key"]

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as sdk:
            api_response = await sdk.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {credential}"},
                json={
                    "model": "gemma-mock",
                    "messages": [{"role": "user", "content": "consume shared allowance"}],
                },
            )
            assert api_response.status_code == 200

        web_response = await client.post(
            "/api/chat/completions",
            json={"model": "gemma-mock", "user_content": "same account, same bucket"},
        )
        assert web_response.status_code == 429
    finally:
        await _cleanup(user_ids=(user_id,))
