from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProgramCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    type: str = Field(pattern="^(A|B)$")
    description: str
    rules: Optional[str] = None
    is_active: bool = True
    categories: Optional[list[str]] = None


class ProgramUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    rules: Optional[str] = None
    is_active: Optional[bool] = None
    categories: Optional[list[str]] = None


class ProgramOut(BaseModel):
    id: UUID
    title: str
    type: str
    description: str
    rules: Optional[str]
    is_active: bool
    categories: Optional[list[str]]
    created_at: datetime

    model_config = {"from_attributes": True}
