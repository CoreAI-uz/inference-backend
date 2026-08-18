"""Import all ORM models so Alembic's ``target_metadata`` sees every table.

Import order matters only for readability; SQLAlchemy resolves relationships lazily.
"""

from app.models.api_content_record import ApiContentRecord
from app.models.api_key import ApiKey
from app.models.auth_identity import AuthIdentity
from app.models.consent_event import ConsentEvent
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.ocr_job import OcrJob
from app.models.usage_event import UsageEvent
from app.models.user import User
from app.models.user_profile import UserProfile

__all__ = [
    "User",
    "ApiKey",
    "AuthIdentity",
    "ApiContentRecord",
    "ConsentEvent",
    "Conversation",
    "Message",
    "OcrJob",
    "UsageEvent",
    "UserProfile",
]
