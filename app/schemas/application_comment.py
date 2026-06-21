from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApplicationCommentCreate(BaseModel):
    body: str = Field(min_length=1)
    is_internal: bool = False


class ApplicationCommentOut(BaseModel):
    id: UUID
    application_id: UUID
    user_id: UUID
    user_name: str = ""
    body: str
    is_internal: bool
    created_at: datetime

    model_config = {"from_attributes": True}
