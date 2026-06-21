from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FAQCreate(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1)
    category: str = "general"
    sort_order: int = 0
    is_published: bool = True


class FAQUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    category: str | None = None
    sort_order: int | None = None
    is_published: bool | None = None


class FAQOut(BaseModel):
    id: UUID
    question: str
    answer: str
    category: str
    sort_order: int
    is_published: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
