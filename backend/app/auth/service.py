"""Auth business logic: register, authenticate, session stitching, usage summary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import Identity
from app.core.security import dummy_verify, hash_password, verify_password
from app.db.types import UsageType
from app.gateway.errors import APIError, ErrorCode
from app.models import AuthIdentity, Conversation, UsageEvent, User, UserProfile
from app.services.data_policy import has_legal_acceptance, record_legal_acceptance


async def register(
    db: AsyncSession,
    email: str,
    password: str,
    locale: str | None,
    display_name: str,
) -> User:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        raise APIError(409, ErrorCode.EMAIL_TAKEN, "email already registered")
    user = User(
        email=email,
        password_hash=hash_password(password),
        locale=locale or "uz",
        display_name=display_name,
    )
    db.add(user)
    await db.flush()
    await record_legal_acceptance(
        db,
        user_id=user.id,
        locale=user.locale,
        source="registration",
        commit=False,
    )
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        dummy_verify(password)  # timing defense
        return None
    if user.password_hash is None:
        dummy_verify(password)
        return None
    if not verify_password(user.password_hash, password):
        return None
    user.last_login_at = func.now()
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_google(
    db: AsyncSession, *, subject: str, email: str
) -> User | None:
    row = (
        await db.execute(
            select(AuthIdentity, User)
            .join(User, User.id == AuthIdentity.user_id)
            .where(
                AuthIdentity.provider == "google",
                AuthIdentity.provider_subject == subject,
            )
        )
    ).one_or_none()
    if row is not None:
        identity, user = row
        now = datetime.now(UTC)
        identity.last_used_at = now
        identity.email_at_link = email
        user.last_login_at = now
        await db.commit()
        await db.refresh(user)
        return user

    existing_email = (
        await db.execute(select(User.id).where(User.email == email))
    ).scalar_one_or_none()
    if existing_email is not None:
        raise APIError(
            409,
            ErrorCode.ACCOUNT_LINK_REQUIRED,
            "An account already exists with this email. Sign in with your password.",
        )
    return None


async def register_google(
    db: AsyncSession,
    *,
    subject: str,
    email: str,
    display_name: str,
    locale: str | None,
) -> User:
    existing_identity = (
        await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == "google",
                AuthIdentity.provider_subject == subject,
            )
        )
    ).scalar_one_or_none()
    if existing_identity is not None:
        user = await db.get(User, existing_identity.user_id)
        if user is None:
            raise APIError(401, ErrorCode.UNAUTHORIZED, "authentication required")
        return user

    existing_email = (
        await db.execute(select(User.id).where(User.email == email))
    ).scalar_one_or_none()
    if existing_email is not None:
        raise APIError(
            409,
            ErrorCode.ACCOUNT_LINK_REQUIRED,
            "An account already exists with this email. Sign in with your password.",
        )

    now = datetime.now(UTC)
    user = User(
        email=email,
        password_hash=None,
        display_name=display_name,
        locale=locale or "uz",
        email_verified_at=now,
        last_login_at=now,
    )
    db.add(user)
    await db.flush()
    db.add(
        AuthIdentity(
            user_id=user.id,
            provider="google",
            provider_subject=subject,
            email_at_link=email,
            last_used_at=now,
        )
    )
    await record_legal_acceptance(
        db,
        user_id=user.id,
        locale=user.locale,
        source="google_registration",
        commit=False,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise APIError(
            409,
            ErrorCode.ACCOUNT_LINK_REQUIRED,
            "This Google account or email is already in use.",
        ) from None
    await db.refresh(user)
    return user


async def auth_methods(db: AsyncSession, user: User) -> dict:
    identities = (
        await db.execute(
            select(AuthIdentity)
            .where(AuthIdentity.user_id == user.id)
            .order_by(AuthIdentity.created_at)
        )
    ).scalars()
    return {
        "password_enabled": user.password_hash is not None,
        "identities": [
            {
                "provider": identity.provider,
                "email": identity.email_at_link,
                "created_at": identity.created_at,
            }
            for identity in identities
        ],
    }


async def link_google_identity(
    db: AsyncSession,
    user: User,
    *,
    subject: str,
    email: str,
) -> AuthIdentity:
    subject_owner = (
        await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == "google",
                AuthIdentity.provider_subject == subject,
            )
        )
    ).scalar_one_or_none()
    if subject_owner is not None:
        if subject_owner.user_id == user.id:
            subject_owner.email_at_link = email
            subject_owner.last_used_at = datetime.now(UTC)
            await db.commit()
            await db.refresh(subject_owner)
            return subject_owner
        raise APIError(
            409,
            ErrorCode.IDENTITY_ALREADY_LINKED,
            "This Google account is connected to another CoreAI account.",
        )

    existing_provider = (
        await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.user_id == user.id,
                AuthIdentity.provider == "google",
            )
        )
    ).scalar_one_or_none()
    if existing_provider is not None:
        raise APIError(
            409,
            ErrorCode.IDENTITY_ALREADY_LINKED,
            "A Google account is already connected.",
        )

    identity = AuthIdentity(
        user_id=user.id,
        provider="google",
        provider_subject=subject,
        email_at_link=email,
        last_used_at=datetime.now(UTC),
    )
    db.add(identity)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise APIError(
            409,
            ErrorCode.IDENTITY_ALREADY_LINKED,
            "This Google account is already connected.",
        ) from None
    await db.refresh(identity)
    return identity


async def unlink_google_identity(db: AsyncSession, user: User) -> None:
    if user.password_hash is None:
        raise APIError(
            409,
            ErrorCode.LAST_SIGN_IN_METHOD,
            "Add another sign-in method before disconnecting Google.",
        )
    await db.execute(
        delete(AuthIdentity).where(
            AuthIdentity.user_id == user.id,
            AuthIdentity.provider == "google",
        )
    )
    await db.commit()


async def stitch_session(db: AsyncSession, session_id: str, user_id: uuid.UUID) -> None:
    """Attribute pre-register anon activity to the new account: re-key the session's
    conversations (their history carries over) and usage events (metering continuity)
    from session_id → user_id."""
    await db.execute(
        update(Conversation)
        .where(Conversation.session_id == session_id, Conversation.user_id.is_(None))
        .values(user_id=user_id)
    )
    await db.execute(
        update(UsageEvent)
        .where(UsageEvent.session_id == session_id, UsageEvent.user_id.is_(None))
        .values(user_id=user_id)
    )
    await db.commit()


async def usage_summary(db: AsyncSession, identity: Identity) -> dict:
    if identity.user_id is not None:
        owner = UsageEvent.user_id == identity.user_id
    else:
        owner = UsageEvent.session_id == identity.session_id
    row = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(UsageEvent.input_tokens), 0),
                func.coalesce(func.sum(UsageEvent.output_tokens), 0),
            ).where(UsageEvent.type == UsageType.CHAT, owner)
        )
    ).one()
    return {"chat_messages": int(row[0]), "tokens_in": int(row[1]), "tokens_out": int(row[2])}


async def build_me(
    db: AsyncSession, identity: Identity, user: User | None, usage: dict, limit_status
) -> dict:
    profile = await db.get(UserProfile, user.id) if user else None
    return {
        "user": (
            {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "locale": user.locale,
                "email_verified": user.email_verified_at is not None,
                "onboarding_status": onboarding_status(profile),
            }
            if user
            else None
        ),
        "is_anon": user is None,
        "session_id": identity.session_id,
        "usage": usage,
        "limits": {
            "chat_cap": limit_status.capacity,
            "chat_remaining": limit_status.remaining,
            "next_message_in": limit_status.next_token_in,
            "is_registered": user is not None,
        },
        "legal_terms_accepted": bool(
            user and await has_legal_acceptance(db, user.id)
        ),
    }


def onboarding_status(profile: UserProfile | None) -> str:
    if profile is None:
        return "not_started"
    if profile.completed_at is not None:
        return "completed"
    if profile.skipped_at is not None:
        return "skipped"
    return "not_started"


def profile_payload(user: User, profile: UserProfile | None) -> dict:
    return {
        "display_name": user.display_name,
        "role": profile.role if profile else None,
        "intended_uses": profile.intended_uses if profile else [],
        "organization_name": profile.organization_name if profile else None,
        "onboarding_status": onboarding_status(profile),
        "onboarding_version": profile.onboarding_version if profile else 1,
        "completed_at": profile.completed_at if profile else None,
        "skipped_at": profile.skipped_at if profile else None,
    }


async def get_profile(db: AsyncSession, user: User) -> dict:
    profile = await db.get(UserProfile, user.id)
    return profile_payload(user, profile)


async def save_onboarding(
    db: AsyncSession,
    user: User,
    *,
    role: str,
    intended_uses: list[str],
    organization_name: str | None,
) -> dict:
    profile = await db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    profile.role = role
    profile.intended_uses = intended_uses
    profile.organization_name = organization_name
    profile.onboarding_version = 1
    profile.completed_at = func.now()
    profile.skipped_at = None
    await db.commit()
    await db.refresh(profile)
    return profile_payload(user, profile)


async def skip_onboarding(db: AsyncSession, user: User) -> dict:
    profile = await db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id, skipped_at=func.now())
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    elif profile.completed_at is None and profile.skipped_at is None:
        profile.skipped_at = func.now()
        await db.commit()
        await db.refresh(profile)
    return profile_payload(user, profile)


async def patch_profile(db: AsyncSession, user: User, changes: dict) -> dict:
    if "display_name" in changes:
        user.display_name = changes.pop("display_name")

    profile_fields = {"role", "intended_uses", "organization_name"}
    supplied_profile_fields = profile_fields.intersection(changes)
    profile = await db.get(UserProfile, user.id)
    if supplied_profile_fields and profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    if profile is not None:
        for field in supplied_profile_fields:
            setattr(profile, field, changes[field])
        if profile.role and profile.intended_uses:
            profile.completed_at = func.now()
            profile.skipped_at = None

    await db.commit()
    await db.refresh(user)
    if profile is not None:
        await db.refresh(profile)
    return profile_payload(user, profile)
