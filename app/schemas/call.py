from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.organization import OrganizationOut
from app.schemas.program import ProgramOut


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

    @model_validator(mode='after')
    def end_after_start(self):
        if self.end_date <= self.start_date:
            raise ValueError('end_date must be after start_date')
        return self


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
    program: Optional[ProgramOut] = None
    organization: Optional[OrganizationOut] = None

    model_config = {"from_attributes": True}
