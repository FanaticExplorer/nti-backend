from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MilestoneCreate(BaseModel):
    application_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    due_date: datetime


class MilestoneStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|in_progress|completed|missed)$")


class MilestoneOut(BaseModel):
    id: UUID
    application_id: UUID
    title: str
    description: Optional[str]
    due_date: datetime
    status: str
    approved_by: Optional[UUID]
    created_at: datetime

    model_config = {"from_attributes": True}
