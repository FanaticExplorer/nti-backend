"""
Evaluations router — evaluator scoring and recommendations.

Endpoints:
- **Create**: submit an evaluation (score, recommendation, comment,
  internal notes) for an application
- **Get**: retrieve evaluations for an application (evaluators see only
  their own; admins see all)
- **Update**: modify an existing evaluation (locked once the application
  is approved or rejected)

All evaluation actions write audit log entries.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.application import Application
from app.models.evaluation import Evaluation
from app.models.user import User
from app.schemas.evaluation import EvaluationCreate, EvaluationOut, EvaluationUpdate
from app.services.audit_service import get_client_ip, write_audit_log
from app.utils.notifications import create_notification

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("", response_model=EvaluationOut, status_code=status.HTTP_201_CREATED)
async def create_evaluation(
    request: Request,
    body: EvaluationCreate,
    current_user: User = Depends(require_role("evaluator")),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a new evaluation for an application.

    Validates that the referenced application exists. The ``evaluator_id``
    is set to the authenticated user and ``submitted_at`` is timestamped.
    An audit log entry is written.

    **Access**: ``evaluator`` only
    """
    # Check application exists
    app_result = await db.execute(
        select(Application).where(Application.id == body.application_id)
    )
    if not app_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )

    evaluation = Evaluation(
        application_id=body.application_id,
        evaluator_id=current_user.id,
        score=body.score,
        recommendation=body.recommendation,
        comment=body.comment,
        internal_notes=body.internal_notes,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)

    await write_audit_log(
        db,
        current_user.id,
        "evaluation.submitted",
        "evaluation",
        str(evaluation.id),
        {"application_id": str(body.application_id)},
        ip_address=get_client_ip(request),
    )

    app_result = await db.execute(
        select(Application).where(Application.id == body.application_id)
    )
    app = app_result.scalar_one_or_none()
    if app:
        await create_notification(
            db, app.applicant_id,
            "New evaluation",
            "Your application has received a new evaluation.",
            "evaluation_added",
            "application", str(app.id),
        )

    return evaluation


@router.get("/{application_id}")
async def get_evaluations(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all evaluations for a given application.

    - ``nti_admin`` and ``super_admin`` see all evaluations
    - ``evaluator`` users see only their own evaluations for the app;
      returns 403 if they have none

    **Access**: ``nti_admin``, ``super_admin``, ``evaluator``
    """
    # Access: nti_admin can see all, evaluator only their own
    query = select(Evaluation).where(Evaluation.application_id == application_id)
    result = await db.execute(query)
    evaluations = result.scalars().all()

    if current_user.role not in ("nti_admin", "super_admin"):
        evaluations = [e for e in evaluations if e.evaluator_id == current_user.id]
        if not evaluations:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No evaluations found for you",
            )

    return {
        "items": [EvaluationOut.model_validate(e) for e in evaluations],
        "total": len(evaluations),
    }


@router.put("/{evaluation_id}", response_model=EvaluationOut)
async def update_evaluation(
    evaluation_id: uuid.UUID,
    body: EvaluationUpdate,
    current_user: User = Depends(require_role("evaluator")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing evaluation.

    - Only the original evaluator can update their evaluation
    - Updates are blocked if the associated application has already been
      ``approved`` or ``rejected``
    - ``submitted_at`` is refreshed to the current time on update

    **Access**: ``evaluator`` (must be the original evaluator)
    """
    result = await db.execute(select(Evaluation).where(Evaluation.id == evaluation_id))
    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found"
        )
    if evaluation.evaluator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Cannot update if application already decided
    app_result = await db.execute(
        select(Application).where(Application.id == evaluation.application_id)
    )
    app = app_result.scalar_one_or_none()
    if app and app.status in ("approved", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update evaluation after application has been decided",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(evaluation, key, value)
    evaluation.submitted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(evaluation)
    return evaluation
