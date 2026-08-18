from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.models.api_key import ApiKey
    from app.models.auth_identity import AuthIdentity
    from app.models.consent_event import ConsentEvent
    from app.models.conversation import Conversation
    from app.models.user_profile import UserProfile


class User(Base, CreatedAtMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    locale: Mapped[str] = mapped_column(String(5), nullable=False, server_default="uz")
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", passive_deletes=True
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user", passive_deletes=True
    )
    consent_events: Mapped[list[ConsentEvent]] = relationship(
        back_populates="user", passive_deletes=True
    )
    auth_identities: Mapped[list[AuthIdentity]] = relationship(
        back_populates="user", passive_deletes=True
    )
    profile: Mapped[UserProfile | None] = relationship(
        back_populates="user", passive_deletes=True, uselist=False
    )
