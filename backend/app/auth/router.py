"""Auth endpoints: register / login / logout / me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth import google as google_service
from app.auth import service as auth_service
from app.auth.cookies import (
    GOOGLE_PENDING_COOKIE,
    clear_auth_cookie,
    clear_google_pending_cookie,
    set_auth_cookie,
    set_google_pending_cookie,
)
from app.auth.dependencies import Identity, _client_ip, get_current_identity, require_user
from app.auth.schemas import (
    AuthMethodsOut,
    AuthProvidersOut,
    GoogleAuthOut,
    GoogleCompleteRegistrationIn,
    GoogleCredentialIn,
    GooglePendingRegistrationOut,
    LegalAcceptanceIn,
    LegalAcceptanceOut,
    LinkedIdentityOut,
    LoginIn,
    MeOut,
    OnboardingIn,
    ProfileOut,
    ProfilePatchIn,
    RegisterIn,
)
from app.core.config import get_settings
from app.core.security import (
    encode_access,
    sign_google_pending,
    unsign_google_pending,
)
from app.gateway.errors import APIError, ErrorCode
from app.gateway.ratelimit import chat_bucket_status, check_login_limit, check_signup_limit
from app.models import User
from app.services.data_policy import LEGAL_POLICY_VERSION, record_legal_acceptance

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _identity_for(request: Request, user: User) -> Identity:
    return Identity(
        session_id=getattr(request.state, "session_id", "no-session"),
        user_id=user.id,
        ip=_client_ip(request),
    )


async def _build_authenticated_me(
    request: Request,
    db: AsyncSession,
    identity: Identity,
    user: User,
) -> dict:
    usage = await auth_service.usage_summary(db, identity)
    limit_status = await chat_bucket_status(request.app.state.redis, identity)
    return await auth_service.build_me(db, identity, user, usage, limit_status)


@router.get("/providers", response_model=AuthProvidersOut)
async def auth_providers():
    client_id = get_settings().google_client_id
    return {"google": {"enabled": bool(client_id), "client_id": client_id}}


@router.post("/google", response_model=GoogleAuthOut)
async def google_auth(
    payload: GoogleCredentialIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    claims = await google_service.verify_google_credential(payload.credential)
    await check_login_limit(request.app.state.redis, _client_ip(request), claims.email)
    user = await auth_service.authenticate_google(
        db, subject=claims.subject, email=claims.email
    )
    if user is None:
        token = sign_google_pending(
            {
                "subject": claims.subject,
                "email": claims.email,
                "display_name": claims.display_name,
            }
        )
        set_google_pending_cookie(response, token)
        return {
            "status": "registration_required",
            "email": claims.email,
            "display_name": claims.display_name or None,
        }

    identity = _identity_for(request, user)
    await auth_service.stitch_session(db, identity.session_id, user.id)
    set_auth_cookie(response, encode_access(user.id))
    clear_google_pending_cookie(response)
    me = await _build_authenticated_me(request, db, identity, user)
    return {"status": "authenticated", "me": me}


@router.post(
    "/google/complete-registration",
    response_model=MeOut,
    status_code=status.HTTP_201_CREATED,
)
async def complete_google_registration(
    payload: GoogleCompleteRegistrationIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    pending_token = request.cookies.get(GOOGLE_PENDING_COOKIE)
    pending = unsign_google_pending(pending_token) if pending_token else None
    if pending is None or not {"subject", "email", "display_name"}.issubset(pending):
        raise APIError(
            401,
            ErrorCode.PENDING_REGISTRATION_EXPIRED,
            "Google registration has expired. Start again.",
        )

    await check_signup_limit(request.app.state.redis, _client_ip(request))
    user = await auth_service.register_google(
        db,
        subject=pending["subject"],
        email=pending["email"],
        display_name=payload.display_name,
        locale=payload.locale,
    )
    identity = _identity_for(request, user)
    await auth_service.stitch_session(db, identity.session_id, user.id)
    set_auth_cookie(response, encode_access(user.id))
    clear_google_pending_cookie(response)
    return await _build_authenticated_me(request, db, identity, user)


@router.get("/google/pending", response_model=GooglePendingRegistrationOut)
async def pending_google_registration(request: Request):
    pending_token = request.cookies.get(GOOGLE_PENDING_COOKIE)
    pending = unsign_google_pending(pending_token) if pending_token else None
    if pending is None or not {"email", "display_name"}.issubset(pending):
        raise APIError(
            401,
            ErrorCode.PENDING_REGISTRATION_EXPIRED,
            "Google registration has expired. Start again.",
        )
    return {"email": pending["email"], "display_name": pending["display_name"]}


@router.get("/identities", response_model=AuthMethodsOut)
async def identities(
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _required_user(identity, db)
    return await auth_service.auth_methods(db, user)


@router.post("/identities/google", response_model=LinkedIdentityOut)
async def link_google_identity(
    payload: GoogleCredentialIn,
    request: Request,
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _required_user(identity, db)
    claims = await google_service.verify_google_credential(payload.credential)
    await check_login_limit(request.app.state.redis, _client_ip(request), claims.email)
    linked = await auth_service.link_google_identity(
        db,
        user,
        subject=claims.subject,
        email=claims.email,
    )
    return {"provider": linked.provider, "email": linked.email_at_link}


@router.delete("/identities/google", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_google_identity(
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _required_user(identity, db)
    await auth_service.unlink_google_identity(db, user)


@router.post("/register", response_model=MeOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    await check_signup_limit(request.app.state.redis, _client_ip(request))
    user = await auth_service.register(
        db, payload.email, payload.password, payload.locale, payload.display_name
    )
    identity = _identity_for(request, user)
    await auth_service.stitch_session(db, identity.session_id, user.id)
    set_auth_cookie(response, encode_access(user.id))
    return await _build_authenticated_me(request, db, identity, user)


async def _required_user(identity: Identity, db: AsyncSession) -> User:
    user = await db.get(User, identity.user_id)
    if user is None:
        raise APIError(401, ErrorCode.UNAUTHORIZED, "authentication required")
    return user


@router.get("/profile", response_model=ProfileOut)
async def profile(
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _required_user(identity, db)
    return await auth_service.get_profile(db, user)


@router.patch("/profile", response_model=ProfileOut)
async def update_profile(
    payload: ProfilePatchIn,
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _required_user(identity, db)
    return await auth_service.patch_profile(db, user, payload.model_dump(exclude_unset=True))


@router.post("/onboarding", response_model=ProfileOut)
async def complete_onboarding(
    payload: OnboardingIn,
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _required_user(identity, db)
    return await auth_service.save_onboarding(
        db,
        user,
        role=payload.role,
        intended_uses=list(payload.intended_uses),
        organization_name=payload.organization_name,
    )


@router.post("/onboarding/skip", response_model=ProfileOut)
async def skip_onboarding(
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _required_user(identity, db)
    return await auth_service.skip_onboarding(db, user)


@router.post("/login", response_model=MeOut)
async def login(
    payload: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    await check_login_limit(request.app.state.redis, _client_ip(request), payload.email)
    user = await auth_service.authenticate(db, payload.email, payload.password)
    if user is None:
        raise APIError(401, ErrorCode.UNAUTHORIZED, "invalid email or password")
    identity = _identity_for(request, user)
    await auth_service.stitch_session(db, identity.session_id, user.id)
    set_auth_cookie(response, encode_access(user.id))
    return await _build_authenticated_me(request, db, identity, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout():
    # Build the response we return and clear the cookie on *it* (setting the header
    # on an injected Response we don't return would be dropped).
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookie(response)
    return response


@router.get("/me", response_model=MeOut)
async def me(
    request: Request,
    identity: Identity = Depends(get_current_identity),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, identity.user_id) if identity.user_id else None
    usage = await auth_service.usage_summary(db, identity)
    limit_status = await chat_bucket_status(request.app.state.redis, identity)
    return await auth_service.build_me(db, identity, user, usage, limit_status)


@router.post("/legal-acceptance", response_model=LegalAcceptanceOut)
async def accept_legal_terms(
    payload: LegalAcceptanceIn,
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, identity.user_id)
    if user is None:
        raise APIError(401, ErrorCode.UNAUTHORIZED, "authentication required")
    await record_legal_acceptance(
        db,
        user_id=user.id,
        locale=user.locale,
        source="api_console",
    )
    return {"accepted": payload.accepted, "policy_version": LEGAL_POLICY_VERSION}
