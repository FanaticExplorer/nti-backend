from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CallCreate(BaseModel):
    program_id: UUID
    organization_id: Optional[UUID] = None
    title: str = Field(min_length=1, max_length=255)
    description: str
    technical_spec: Optional[str] = None
    budget: Optional[float] = None
    product_owner_id: Optional[UUID] = None
    start_date: datetime
    end_date: datetime


class CallUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    technical_spec: Optional[str] = None
    budget: Optional[float] = None
    product_owner_id: Optional[UUID] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class CallStatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|open|matching|assigned|in_progress|closed)$")


class CallOut(BaseModel):
    id: UUID
    program_id: UUID
    organization_id: Optional[UUID]
    title: str
    description: str
    technical_spec: Optional[str]
    budget: Optional[float]
    product_owner_id: Optional[UUID]
    start_date: datetime
    end_date: datetime
    status: str
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
