from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: UUID
    title: str
    body: str
    action_type: str
    entity_type: str | None
    entity_id: str | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
