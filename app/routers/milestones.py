"""
Milestones router — tracking application milestones.

Endpoints:
- **Create**: ``nti_admin`` or ``mentor`` creates a milestone for an application
- **List**: retrieve all milestones for an application with access control
- **Update status**: mark a milestone as completed (or other status);
  the approving user is recorded

Milestones represent checkpoints in the application lifecycle after
approval (e.g. during onboarding or active phases).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.application import Application
from app.models.milestone import Milestone
from app.models.user import User
from app.schemas.milestone import MilestoneCreate, MilestoneOut, MilestoneStatusUpdate

router = APIRouter(prefix="/milestones", tags=["milestones"])


@router.post("", response_model=MilestoneOut, status_code=status.HTTP_201_CREATED)
async def create_milestone(
    body: MilestoneCreate,
    current_user: User = Depends(require_role("nti_admin", "mentor")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new milestone for an application.

    Validates that the referenced application exists.

    **Access**: ``nti_admin``, ``mentor``
    """
    app_result = await db.execute(
        select(Application).where(Application.id == body.application_id)
    )
    if not app_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )

    milestone = Milestone(**body.model_dump())
    db.add(milestone)
    await db.commit()
    await db.refresh(milestone)
    return milestone


@router.get("/{application_id}")
async def list_milestones(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all milestones for a given application.

    **Access control**:
    - ``nti_admin`` and ``mentor`` can view milestones for any application
    - The original applicant can view their own application's milestones
    - All other roles receive a 403
    """
    app_result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    app = app_result.scalar_one_or_none()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )

    allowed = ("nti_admin", "mentor")
    if current_user.role not in allowed and app.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    result = await db.execute(
        select(Milestone).where(Milestone.application_id == application_id)
    )
    milestones = result.scalars().all()
    return {
        "items": [MilestoneOut.model_validate(m) for m in milestones],
        "total": len(milestones),
    }


@router.patch("/{milestone_id}/status", response_model=MilestoneOut)
async def update_milestone_status(
    milestone_id: uuid.UUID,
    body: MilestoneStatusUpdate,
    current_user: User = Depends(require_role("mentor", "nti_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update the status of a milestone.

    When the status is set to ``completed``, the ``approved_by`` field
    is set to the authenticated user's ID.

    **Access**: ``mentor``, ``nti_admin``
    """
    result = await db.execute(select(Milestone).where(Milestone.id == milestone_id))
    milestone = result.scalar_one_or_none()
    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found"
        )

    milestone.status = body.status
    if body.status == "completed":
        milestone.approved_by = current_user.id

    await db.commit()
    await db.refresh(milestone)
    return milestone
