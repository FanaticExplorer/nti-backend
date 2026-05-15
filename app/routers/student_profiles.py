"""
Student profiles router — student/team-leader profile management.

Endpoints:
- **Create**: a student creates their profile (one profile per user)
- **Get my profile**: retrieve the authenticated user's own profile
- **Update my profile**: modify the authenticated user's own profile
- **Get by user ID**: admins, mentors, and evaluators can look up any
  student's profile by user ID

Student profiles store additional information beyond the base user model
(e.g. university, field of study, skills).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.schemas.student_profile import (
    StudentProfileCreate,
    StudentProfileOut,
    StudentProfileUpdate,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("", response_model=StudentProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: StudentProfileCreate,
    current_user: User = Depends(require_role("student", "team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a student profile for the current user.

    Returns 409 if the user already has a profile (one profile per user).
    The ``user_id`` is set automatically from the authenticated user.

    **Access**: ``student``, ``team_leader``
    """
    result = await db.execute(
        select(StudentProfile).where(StudentProfile.user_id == current_user.id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile already exists",
        )

    profile = StudentProfile(user_id=current_user.id, **body.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/me", response_model=StudentProfileOut)
async def get_my_profile(
    current_user: User = Depends(require_role("student", "team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the current user's own student profile.

    Returns 404 if no profile has been created yet.

    **Access**: ``student``, ``team_leader``
    """
    result = await db.execute(
        select(StudentProfile).where(StudentProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )
    return profile


@router.put("/me", response_model=StudentProfileOut)
async def update_my_profile(
    body: StudentProfileUpdate,
    current_user: User = Depends(require_role("student", "team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update the current user's student profile.

    Only fields present in the request body are updated (partial update).
    Returns 404 if no profile exists yet.

    **Access**: ``student``, ``team_leader``
    """
    result = await db.execute(
        select(StudentProfile).where(StudentProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)

    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/{user_id}", response_model=StudentProfileOut)
async def get_profile_by_user_id(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role("nti_admin", "mentor", "evaluator")),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a student profile by the user's ID.

    Used by admins, mentors, and evaluators to look up student details
    during the evaluation and mentorship process.

    Returns 404 if the user has no profile.

    **Access**: ``nti_admin``, ``mentor``, ``evaluator``
    """
    result = await db.execute(
        select(StudentProfile).where(StudentProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )
    return profile
