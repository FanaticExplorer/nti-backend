from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.auth import UserOut
from app.schemas.call import CallOut
from app.schemas.team import TeamOut


class ApplicationCreate(BaseModel):
    call_id: UUID
    team_id: Optional[UUID] = None
    tech_spec_id: Optional[UUID] = None
    form_data: dict = {}


class ApplicationUpdate(BaseModel):
    form_data: Optional[dict] = None


class ApplicationStatusUpdate(BaseModel):
    status: str
    comment: Optional[str] = None


class ApplicationOut(BaseModel):
    id: UUID
    call_id: UUID
    team_id: Optional[UUID]
    tech_spec_id: Optional[UUID]
    applicant_id: UUID
    form_data: dict
    status: str
    is_draft: bool
    submitted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationDetailOut(ApplicationOut):
    call: Optional["CallOut"] = None
    team: Optional["TeamOut"] = None
    applicant: Optional["UserOut"] = None


class ApplicationStatusHistoryOut(BaseModel):
    id: UUID
    application_id: UUID
    old_status: str
    new_status: str
    changed_by: UUID
    comment: Optional[str]
    changed_at: datetime

    model_config = {"from_attributes": True}
