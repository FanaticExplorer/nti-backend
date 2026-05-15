from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    program_type: str = Field(pattern="^(A|B)$")


class TeamOut(BaseModel):
    id: UUID
    name: str
    leader_id: UUID
    program_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamDetailOut(TeamOut):
    members: list = []
