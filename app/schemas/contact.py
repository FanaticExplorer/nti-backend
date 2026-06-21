from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ContactMessageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    message: str = Field(min_length=1, max_length=5000)


class ContactMessageOut(BaseModel):
    id: UUID
    name: str
    email: str
    message: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
