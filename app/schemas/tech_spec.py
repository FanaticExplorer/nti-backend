from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TechSpecBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    budget: str | None = None
    product_owner_id: UUID | None = None


class TechSpecCreate(TechSpecBase):
    call_id: UUID


class TechSpecUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    budget: str | None = None
    product_owner_id: UUID | None = None


class TechSpecStatusUpdate(BaseModel):
    status: str


class TechSpecOut(BaseModel):
    id: UUID
    organization_id: UUID
    call_id: UUID
    product_owner_id: UUID | None
    title: str
    description: str
    budget: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TechSpecDetailOut(TechSpecOut):
    organization_name: str | None = None
    product_owner_name: str | None = None
    application_count: int = 0
