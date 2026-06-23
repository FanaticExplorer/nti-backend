from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.application import ApplicationDetailOut


class MentorshipCreate(BaseModel):
    application_id: UUID
    mentor_id: UUID


class MentorshipLogCreate(BaseModel):
    content: str


class MentorshipLogOut(BaseModel):
    id: UUID
    mentorship_id: UUID
    logged_by: UUID
    content: str
    logged_at: datetime

    model_config = {"from_attributes": True}


class MentorshipOut(BaseModel):
    id: UUID
    application_id: UUID
    mentor_id: UUID
    assigned_at: datetime
    is_active: bool
    application: Optional[ApplicationDetailOut] = None

    model_config = {"from_attributes": True}
