from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

RoleCode = Literal[
    "software_developer",
    "ml_data_specialist",
    "researcher",
    "student",
    "educator",
    "business_owner_founder",
    "product_business",
    "marketing_content",
    "government_public_sector",
    "other",
]

IntendedUseCode = Literal[
    "general_assistant",
    "writing_translation",
    "programming",
    "data_analysis",
    "research_education",
    "api_application",
    "business_workflows",
    "model_evaluation",
    "other",
]


def _clean_text(value: str) -> str:
    return " ".join(value.split())


class RegisterIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    locale: str | None = Field(default=None, max_length=5)
    legal_terms_accepted: Literal[True]

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("preferred name is required")
        return value


class LegalAcceptanceIn(BaseModel):
    accepted: Literal[True]


class LegalAcceptanceOut(BaseModel):
    accepted: bool
    policy_version: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    locale: str
    email_verified: bool
    onboarding_status: Literal["not_started", "completed", "skipped"]


class ProfileOut(BaseModel):
    display_name: str | None
    role: RoleCode | None
    intended_uses: list[IntendedUseCode]
    organization_name: str | None
    onboarding_status: Literal["not_started", "completed", "skipped"]
    onboarding_version: int
    completed_at: datetime | None
    skipped_at: datetime | None


class OnboardingIn(BaseModel):
    role: RoleCode
    intended_uses: list[IntendedUseCode] = Field(min_length=1, max_length=9)
    organization_name: str | None = Field(default=None, max_length=160)

    @field_validator("intended_uses")
    @classmethod
    def unique_intended_uses(cls, value: list[IntendedUseCode]) -> list[IntendedUseCode]:
        if len(value) != len(set(value)):
            raise ValueError("intended uses must be unique")
        return value

    @field_validator("organization_name")
    @classmethod
    def clean_organization(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_text(value) or None


class ProfilePatchIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    role: RoleCode | None = None
    intended_uses: list[IntendedUseCode] | None = Field(default=None, min_length=1, max_length=9)
    organization_name: str | None = Field(default=None, max_length=160)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("preferred name cannot be cleared")
        value = _clean_text(value)
        if not value:
            raise ValueError("preferred name is required")
        return value

    @field_validator("role")
    @classmethod
    def role_cannot_be_cleared(cls, value: RoleCode | None) -> RoleCode:
        if value is None:
            raise ValueError("role cannot be cleared")
        return value

    @field_validator("intended_uses")
    @classmethod
    def unique_intended_uses(
        cls, value: list[IntendedUseCode] | None
    ) -> list[IntendedUseCode]:
        if value is None:
            raise ValueError("intended uses cannot be cleared")
        if len(value) != len(set(value)):
            raise ValueError("intended uses must be unique")
        return value

    @field_validator("organization_name")
    @classmethod
    def clean_organization(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_text(value) or None


class UsageOut(BaseModel):
    chat_messages: int
    tokens_in: int
    tokens_out: int


class LimitsOut(BaseModel):
    chat_cap: int
    chat_remaining: int
    next_message_in: int
    is_registered: bool


class MeOut(BaseModel):
    user: UserOut | None
    is_anon: bool
    session_id: str
    usage: UsageOut
    limits: LimitsOut
    legal_terms_accepted: bool


class AuthProviderOut(BaseModel):
    enabled: bool
    client_id: str | None


class AuthProvidersOut(BaseModel):
    google: AuthProviderOut


class GoogleCredentialIn(BaseModel):
    credential: str = Field(min_length=100, max_length=8192)


class GoogleAuthOut(BaseModel):
    status: Literal["authenticated", "registration_required"]
    me: MeOut | None = None
    email: str | None = None
    display_name: str | None = None


class GoogleCompleteRegistrationIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    locale: str | None = Field(default=None, max_length=5)
    legal_terms_accepted: Literal[True]

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("preferred name is required")
        return value


class GooglePendingRegistrationOut(BaseModel):
    email: str
    display_name: str


class AuthIdentityOut(BaseModel):
    provider: str
    email: str | None
    created_at: datetime


class AuthMethodsOut(BaseModel):
    password_enabled: bool
    identities: list[AuthIdentityOut]


class LinkedIdentityOut(BaseModel):
    provider: str
    email: str
