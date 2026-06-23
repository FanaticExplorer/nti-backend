from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EvaluationCreate(BaseModel):
    application_id: UUID
    score: Optional[float] = Field(None, ge=0, le=10)
    recommendation: Optional[str] = Field(
        None, pattern="^(approve|reject|request_revision|revision)$"
    )
    comment: Optional[str] = None
    internal_notes: Optional[str] = None


class EvaluationUpdate(BaseModel):
    score: Optional[float] = Field(None, ge=0, le=10)
    recommendation: Optional[str] = Field(
        None, pattern="^(approve|reject|request_revision|revision)$"
    )
    comment: Optional[str] = None
    internal_notes: Optional[str] = None


class EvaluationOut(BaseModel):
    id: UUID
    application_id: UUID
    evaluator_id: UUID
    score: Optional[float]
    recommendation: Optional[str]
    comment: Optional[str]
    internal_notes: Optional[str]
    submitted_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
