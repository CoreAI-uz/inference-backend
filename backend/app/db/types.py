"""Shared DB-level enums (native Postgres enum types).

Enum values are additive-only: never remove or renumber a value (that needs a
non-transactional ``ALTER TYPE``). Add new ones at the end.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class FinishReason(StrEnum):
    STOP = "stop"          # completed normally
    STOPPED = "stopped"    # client stopped / mid-stream abort → partial persisted
    LENGTH = "length"      # hit max tokens / context limit


class OcrStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    EXPIRED = "expired"    # files swept after retention; row + metrics kept


class UsageType(StrEnum):
    CHAT = "chat"
    OCR = "ocr"


# --- Rate-limit logic enums (not DB-backed) ---
class Tier(StrEnum):
    ANON = "anon"
    REGISTERED = "registered"


class Bucket(StrEnum):
    CHAT = "chat"
    OCR = "ocr"
    SIGNUP = "signup"
    LOGIN = "login"


# Postgres enum type names (referenced by both the ORM and the migration).
MESSAGE_ROLE_ENUM = "message_role"
FINISH_REASON_ENUM = "finish_reason"
OCR_STATUS_ENUM = "ocr_status"
USAGE_TYPE_ENUM = "usage_type"


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Native PG enum column type whose labels are the enum *values* (lowercase),
    matching the labels created in the migration. ``create_type=False`` because the
    migration owns type creation.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )
