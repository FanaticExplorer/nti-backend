from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ico: Optional[str] = None
    sector: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    contact_email: str


class OrganizationOut(BaseModel):
    id: UUID
    name: str
    ico: Optional[str]
    sector: Optional[str]
    description: Optional[str]
    website: Optional[str]
    contact_email: str
    is_approved: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    user_id: UUID
    role_in_org: Optional[str] = None
