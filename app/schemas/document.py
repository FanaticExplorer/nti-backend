from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: UUID
    application_id: UUID | None
    uploaded_by: UUID
    filename: str
    file_size: int
    mime_type: str
    classification: str
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}
