"""Pure-logic unit tests (no DB/Redis/network).

Integration tests over the HTTP surface land in M5 once real login makes them clean.
"""

import uuid

from app.core.security import (
    decode_access,
    encode_access,
    hash_password,
    verify_password,
)
from app.gateway.events import StreamEvent, sse
from app.gateway.safety import estimate_tokens, trim_to_context
from app.services.titles import DEFAULT_TITLE, derive_title


def test_estimate_tokens():
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 40) == 10


def test_trim_keeps_system_and_newest():
    msgs = [{"role": "system", "content": "sys"}] + [
        {"role": "user", "content": "x" * 4000} for _ in range(50)
    ]
    out = trim_to_context(msgs, max_context=2048, reserve=512)
    assert out[0]["role"] == "system"       # system always kept
    assert len(out) < len(msgs)             # trimmed
    assert out[-1] is msgs[-1]              # newest preserved


def test_derive_title():
    assert derive_title("") == DEFAULT_TITLE
    assert derive_title("  hello   world ") == "hello world"
    assert derive_title("a " * 60).endswith("…")
    # Uzbek Latin modifier letter U+02BB preserved
    assert derive_title("Salom oʻzbek gʻalaba") == "Salom oʻzbek gʻalaba"


def test_sse_framing():
    frame = sse(StreamEvent.DELTA, {"content": "hi"})
    assert frame.startswith("event: delta\n")
    assert 'data: {"content": "hi"}' in frame
    assert frame.endswith("\n\n")
    # ensure_ascii=False keeps non-ASCII intact
    assert "oʻ" in sse(StreamEvent.DELTA, {"content": "oʻ"})


def test_password_hash_roundtrip():
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse battery staple")
    assert not verify_password(h, "wrong")


def test_jwt_roundtrip():
    uid = uuid.uuid4()
    token = encode_access(uid)
    assert decode_access(token) == uid
    assert decode_access("garbage.token.value") is None


async def test_moderate_input_allows():
    from app.auth.dependencies import Identity
    from app.gateway.safety import moderate_input

    ident = Identity(session_id="s", user_id=None, ip="127.0.0.1")
    result = await moderate_input([{"role": "user", "content": "hello"}], ident)
    assert result.allowed is True


def test_client_ip_trusted_proxy(monkeypatch):
    from app.auth import dependencies as deps
    from app.core.config import get_settings

    class FakeReq:
        headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}

        class client:
            host = "10.0.0.1"

    settings = get_settings()
    monkeypatch.setattr(settings, "trusted_proxy", True)
    assert deps._client_ip(FakeReq()) == "203.0.113.9"  # real client from XFF
    monkeypatch.setattr(settings, "trusted_proxy", False)
    assert deps._client_ip(FakeReq()) == "10.0.0.1"  # peer IP


def test_allowed_hosts_are_parsed_for_trusted_host_middleware():
    from app.core.config import Settings

    settings = Settings(allowed_hosts="chat.coreai.uz, localhost")
    assert settings.allowed_host_list == ["chat.coreai.uz", "localhost"]


def test_cookie_domain_is_not_configurable():
    from app.core.config import Settings

    assert "cookie_domain" not in Settings.model_fields


def test_anonymous_chat_retention_defaults_to_30_days():
    from app.core.config import Settings

    assert Settings().anon_conv_retention_days == 30
