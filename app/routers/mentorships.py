"""
Mentorships router — mentor assignment and mentorship session logs.

Endpoints:
- **Assign**: ``nti_admin`` pairs a mentor with an application
- **My mentorships**: mentors list their assigned applications
- **Get mentorship**: retrieve a single mentorship with access control
- **Logs**: mentors can create and read session logs for their mentorships

Access control ensures mentors can only view and log to their own
mentorships, while admins have full visibility.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.application import Application
from app.models.mentorship import Mentorship
from app.models.mentorship_log import MentorshipLog
from app.models.user import User
from app.schemas.mentorship import (
    MentorshipCreate,
    MentorshipLogCreate,
    MentorshipLogOut,
    MentorshipOut,
)
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/mentorships", tags=["mentorships"])


@router.post("", response_model=MentorshipOut, status_code=status.HTTP_201_CREATED)
async def assign_mentor(
    body: MentorshipCreate,
    current_user: User = Depends(require_role("nti_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Assign a mentor to an application.

    Validates that both the application and the mentor user exist.
    Creates a mentorship record and writes an audit log entry.

    **Access**: ``nti_admin`` only
    """
    # Check application
    app_result = await db.execute(
        select(Application).where(Application.id == body.application_id)
    )
    if not app_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )

    # Check mentor exists and has mentor role
    mentor_result = await db.execute(select(User).where(User.id == body.mentor_id))
    mentor = mentor_result.scalar_one_or_none()
    if not mentor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mentor not found"
        )
    if mentor.role != "mentor":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assigned user does not have mentor role",
        )

    mentorship = Mentorship(
        application_id=body.application_id,
        mentor_id=body.mentor_id,
    )
    db.add(mentorship)
    await db.commit()
    await db.refresh(mentorship)

    await write_audit_log(
        db,
        current_user.id,
        "mentorship.assigned",
        "mentorship",
        str(mentorship.id),
        {"application_id": str(body.application_id), "mentor_id": str(body.mentor_id)},
    )

    return mentorship


@router.get("/my")
async def get_my_mentorships(
    current_user: User = Depends(require_role("mentor")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return all mentorships assigned to the current mentor.

    **Access**: ``mentor`` only
    """
    result = await db.execute(
        select(Mentorship).where(Mentorship.mentor_id == current_user.id)
    )
    mentorships = result.scalars().all()
    return {
        "items": [MentorshipOut.model_validate(m) for m in mentorships],
        "total": len(mentorships),
    }


@router.get("/{mentorship_id}", response_model=MentorshipOut)
async def get_mentorship(
    mentorship_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a single mentorship by ID.

    **Access control**:
    - ``nti_admin`` and ``super_admin`` can view any mentorship
    - The assigned mentor can view their own mentorships
    - All other roles receive a 403
    """
    result = await db.execute(select(Mentorship).where(Mentorship.id == mentorship_id))
    mentorship = result.scalar_one_or_none()
    if not mentorship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mentorship not found"
        )

    allowed = ("nti_admin", "super_admin")
    if current_user.role not in allowed and mentorship.mentor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    return mentorship


@router.post(
    "/{mentorship_id}/logs",
    response_model=MentorshipLogOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_mentorship_log(
    mentorship_id: uuid.UUID,
    body: MentorshipLogCreate,
    current_user: User = Depends(require_role("mentor")),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a session log entry to a mentorship.

    Only the assigned mentor for this mentorship can add logs.
    The ``logged_by`` field is set to the authenticated user.

    **Access**: ``mentor`` (must be the assigned mentor)
    """
    result = await db.execute(select(Mentorship).where(Mentorship.id == mentorship_id))
    mentorship = result.scalar_one_or_none()
    if not mentorship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mentorship not found"
        )
    if mentorship.mentor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your mentorship"
        )

    log = MentorshipLog(
        mentorship_id=mentorship_id,
        logged_by=current_user.id,
        content=body.content,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@router.get("/{mentorship_id}/logs")
async def get_mentorship_logs(
    mentorship_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all session logs for a mentorship.

    Ordered by ``logged_at`` descending (most recent first).

    **Access control**: same as ``GET /{mentorship_id}``
    """
    result = await db.execute(select(Mentorship).where(Mentorship.id == mentorship_id))
    mentorship = result.scalar_one_or_none()
    if not mentorship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mentorship not found"
        )

    allowed = ("nti_admin", "super_admin")
    if current_user.role not in allowed and mentorship.mentor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    log_result = await db.execute(
        select(MentorshipLog)
        .where(MentorshipLog.mentorship_id == mentorship_id)
        .order_by(MentorshipLog.logged_at.desc())
    )
    logs = log_result.scalars().all()
    return {
        "items": [MentorshipLogOut.model_validate(lg) for lg in logs],
        "total": len(logs),
    }
