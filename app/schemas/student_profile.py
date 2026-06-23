from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class StudentProfileCreate(BaseModel):
    university: str
    faculty: str
    study_program: str
    year_of_study: int = Field(ge=1, le=10)
    gpa: Optional[float] = Field(None, ge=0.0, le=5.0)
    has_academic_debt: bool = False
    skills: Optional[list] = None
    bio: Optional[str] = None


class StudentProfileUpdate(BaseModel):
    university: Optional[str] = None
    faculty: Optional[str] = None
    study_program: Optional[str] = None
    year_of_study: Optional[int] = Field(None, ge=1, le=10)
    gpa: Optional[float] = Field(None, ge=0.0, le=5.0)
    has_academic_debt: Optional[bool] = None
    skills: Optional[list] = None
    bio: Optional[str] = None


class StudentProfileOut(BaseModel):
    id: UUID
    user_id: UUID
    university: str
    faculty: str
    study_program: str
    year_of_study: int
    gpa: Optional[float]
    has_academic_debt: bool
    skills: Optional[list]
    cv_document_id: Optional[UUID]
    bio: Optional[str]

    model_config = {"from_attributes": True}
