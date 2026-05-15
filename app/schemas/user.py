from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserUpdateRole(BaseModel):
    role: str = Field(
        pattern="^(visitor|student|team_leader|firm|mentor|evaluator|content_editor|nti_admin|super_admin)$"
    )


class UserListOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    is_email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}
