"""
Applications router — full lifecycle management of student applications.

Endpoints cover:
- Creating draft applications
- Listing applications (own or all, depending on role)
- Retrieving a single application with access control
- Updating draft applications
- Submitting applications (with Program A / Program B validation)
- Status transitions following a predefined state machine
- Fetching the status change history of an application

Status transitions are validated against ``VALID_TRANSITIONS``, a dictionary
that defines the allowed next status(es) for each current status.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.application import Application
from app.models.application_comment import ApplicationComment
from app.models.application_status_history import ApplicationStatusHistory
from app.models.call import Call
from app.models.document import Document
from app.models.program import Program
from app.models.student_profile import StudentProfile
from app.models.team import Team, team_members
from app.models.tech_spec import TechSpec
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetailOut,
    ApplicationOut,
    ApplicationStatusHistoryOut,
    ApplicationStatusUpdate,
    ApplicationUpdate,
)
from app.schemas.application_comment import (
    ApplicationCommentCreate,
    ApplicationCommentOut,
)
from app.services.audit_service import get_client_ip, write_audit_log
from app.utils.email import send_application_submitted, send_status_change
from app.utils.notifications import create_notification

router = APIRouter(prefix="/applications", tags=["applications"])

VALID_TRANSITIONS = {
    "draft": ["submitted"],
    "submitted": ["formally_verified"],
    "formally_verified": ["under_evaluation"],
    "under_evaluation": ["approved", "rejected", "revision_requested"],
    "revision_requested": ["submitted"],
    "approved": ["onboarding"],
    "onboarding": ["active"],
    "active": ["paused", "completed"],
    "paused": ["active"],
    "completed": ["archived"],
    "rejected": [],
    "archived": [],
}


async def _get_app(application_id: uuid.UUID, db: AsyncSession) -> Application:
    """
    Fetch an application by ID or raise 404.

    Internal helper used by multiple endpoints to avoid repetitive
    lookup-and-raise logic.
    """
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    return app


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_application(
    body: ApplicationCreate,
    current_user: User = Depends(require_role("student", "team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new draft application.

    The application is created in ``draft`` status for the currently
    authenticated student or team leader. The ``applicant_id`` is set
    automatically from the authenticated user.

    **Access**: ``student``, ``team_leader``
    """
    if body.tech_spec_id:
        ts_result = await db.execute(
            select(TechSpec).where(TechSpec.id == body.tech_spec_id)
        )
        ts = ts_result.scalar_one_or_none()
        if not ts:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Tech spec not found"
            )
        call_result = await db.execute(
            select(Call).where(Call.id == body.call_id)
        )
        call = call_result.scalar_one_or_none()
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
            )
        program_result = await db.execute(
            select(Program).where(Program.id == call.program_id)
        )
        program = program_result.scalar_one_or_none()
        if not program or program.type != "B":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Tech spec ID can only be used for Program B applications",
            )
        if ts.call_id != body.call_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Tech spec does not belong to the specified call",
            )

    app = Application(
        call_id=body.call_id,
        team_id=body.team_id,
        tech_spec_id=body.tech_spec_id,
        applicant_id=current_user.id,
        form_data=body.form_data,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@router.get("/my")
async def get_my_applications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role("student", "team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return paginated list of the current user's own applications.

    **Access**: ``student``, ``team_leader``
    """
    result = await db.execute(
        select(Application)
        .where(Application.applicant_id == current_user.id)
        .offset(skip)
        .limit(limit)
    )
    apps = result.scalars().all()
    total_result = await db.execute(
        select(func.count(Application.id)).where(Application.applicant_id == current_user.id)
    )
    total = total_result.scalar() or 0
    return {
        "items": [ApplicationOut.model_validate(a) for a in apps],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("")
async def list_applications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    call_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_role("nti_admin", "evaluator", "mentor")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a paginated, filterable list of all applications.

    Supports optional filtering by:
    - **status**: application status (e.g. ``submitted``, ``approved``)
    - **call_id**: UUID of a specific call for proposals

    **Access**: ``nti_admin``, ``evaluator``, ``mentor``
    """
    query = select(Application)
    if status_filter:
        query = query.where(Application.status == status_filter)
    if call_id:
        query = query.where(Application.call_id == call_id)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    apps = result.scalars().all()

    count_query = select(func.count(Application.id))
    if status_filter:
        count_query = count_query.where(Application.status == status_filter)
    if call_id:
        count_query = count_query.where(Application.call_id == call_id)
    total = (await db.execute(count_query)).scalar() or 0

    return {
        "items": [ApplicationOut.model_validate(a) for a in apps],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{application_id}", response_model=ApplicationDetailOut)
async def get_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a single application by ID.

    Includes nested ``call``, ``team``, and ``applicant`` objects.

    **Access control**:
    - ``nti_admin``, ``evaluator``, ``mentor`` can view any application
    - The original applicant can view their own application
    - All other roles receive a 403
    """
    result = await db.execute(
        select(Application)
        .options(
            selectinload(Application.call),
            selectinload(Application.team),
            selectinload(Application.applicant),
        )
        .where(Application.id == application_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    allowed = ("nti_admin", "evaluator", "mentor")
    if current_user.role not in allowed and app.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )
    return ApplicationDetailOut.model_validate(app)


@router.put("/{application_id}", response_model=ApplicationOut)
async def update_application(
    application_id: uuid.UUID,
    body: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a draft application.

    Only the original applicant can edit, and only while the application
    is still in ``draft`` status (``is_draft == True``). Once submitted,
    the application becomes immutable through this endpoint.

    **Access**: the applicant who created the application
    """
    app = await _get_app(application_id, db)
    if app.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )
    if not app.is_draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only edit draft applications",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(app, key, value)
    await db.commit()
    await db.refresh(app)
    return app


@router.post("/{application_id}/submit", response_model=ApplicationOut)
async def submit_application(
    request: Request,
    application_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("student", "team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a draft application for evaluation.

    Performs validation depending on the program type:

    **Program A** (team-based, incubation):
    - Requires a team with at least 3 members
    - Every team member must have a student profile
    - Requires 6 specific documents: Executive Summary, Technical
      Architecture, Roadmap, Budget plan, Risk analysis, Monetization model

    **Program B** (individual, pre-incubation):
    - No team or document requirements enforced at submission

    On success the status transitions from ``draft`` to ``submitted``,
    ``is_draft`` is set to ``False``, and ``submitted_at`` is timestamped.
    A status history entry and an audit log entry are created.
    A confirmation email is queued for the applicant.

    **Access**: ``student``, ``team_leader`` (must be the applicant)
    """
    app = await _get_app(application_id, db)
    if app.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )
    if not app.is_draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Application already submitted",
        )

    call_result = await db.execute(select(Call).where(Call.id == app.call_id))
    call = call_result.scalar_one_or_none()
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
        )

    program_result = await db.execute(
        select(Program).where(Program.id == call.program_id)
    )
    program = program_result.scalar_one_or_none()

    # Program A validation
    if program and program.type == "A":
        if not app.team_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Program A requires a team",
            )

        team_result = await db.execute(select(Team).where(Team.id == app.team_id))
        team = team_result.scalar_one_or_none()
        if team:
            member_count_result = await db.execute(
                select(team_members).where(team_members.c.team_id == team.id)
            )
            members = member_count_result.all()
            if len(members) < 3:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Team must have at least 3 members for Program A",
                )

            for member in members:
                profile_result = await db.execute(
                    select(StudentProfile).where(
                        StudentProfile.user_id == member.user_id
                    )
                )
                if not profile_result.scalar_one_or_none():
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=f"Team member {member.user_id} has no student profile",
                    )

        # Program A: require 6 documents
        required_docs = [
            "Executive Summary",
            "Technical Architecture",
            "Roadmap",
            "Budget plan",
            "Risk analysis",
            "Monetization model",
        ]
        docs_result = await db.execute(
            select(Document).where(Document.application_id == app.id)
        )
        uploaded_filenames = [d.filename.lower() for d in docs_result.scalars().all()]
        missing = [
            doc
            for doc in required_docs
            if not any(doc.lower() in fn for fn in uploaded_filenames)
        ]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Missing required documents for Program A: {', '.join(missing)}",
            )

    # Program B validation
    if program and program.type == "B":
        if not app.tech_spec_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Program B requires a tech spec ID",
            )
        ts_result = await db.execute(
            select(TechSpec).where(TechSpec.id == app.tech_spec_id)
        )
        ts = ts_result.scalar_one_or_none()
        if not ts:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Linked tech spec not found"
            )
        if ts.status not in ("published", "in_pairing"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Tech spec must be published or in_pairing, current status: {ts.status}",
            )

    old_status = app.status
    app.status = "submitted"
    app.is_draft = False
    app.submitted_at = datetime.now(timezone.utc)

    history = ApplicationStatusHistory(
        application_id=app.id,
        old_status=old_status,
        new_status="submitted",
        changed_by=current_user.id,
        comment="Application submitted",
    )
    db.add(history)
    await db.commit()
    await db.refresh(app)

    await write_audit_log(
        db,
        current_user.id,
        "application.status_changed",
        "application",
        str(app.id),
        {"old_status": old_status, "new_status": "submitted"},
        ip_address=get_client_ip(request),
    )

    # Email applicant
    user_result = await db.execute(select(User).where(User.id == app.applicant_id))
    applicant = user_result.scalar_one_or_none()
    if applicant:
        background_tasks.add_task(send_application_submitted, applicant.email)

    await create_notification(
        db, app.applicant_id,
        "Application submitted",
        "Your application has been submitted and is being processed.",
        "application_submitted",
        "application", str(app.id),
    )

    return app


@router.patch("/{application_id}/status", response_model=ApplicationOut)
async def change_application_status(
    request: Request,
    application_id: uuid.UUID,
    body: ApplicationStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("nti_admin", "evaluator")),
    db: AsyncSession = Depends(get_db),
):
    """
    Transition an application to a new status.

    Validates the transition against ``VALID_TRANSITIONS``. If the
    requested status is not an allowed next step from the current status,
    a 422 error is returned listing the allowed transitions.

    Creates a status history entry, an audit log entry, and queues a
    notification email to the applicant.

    **Access**: ``nti_admin``, ``evaluator``
    """
    app = await _get_app(application_id, db)
    old_status = app.status

    allowed = VALID_TRANSITIONS.get(old_status, [])
    if body.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Cannot transition from '{old_status}' to '{body.status}'. Allowed: {allowed}",
        )

    app.status = body.status
    if body.status != "draft":
        app.is_draft = False

    history = ApplicationStatusHistory(
        application_id=app.id,
        old_status=old_status,
        new_status=body.status,
        changed_by=current_user.id,
        comment=body.comment,
    )
    db.add(history)
    await db.commit()
    await db.refresh(app)

    if body.status == "approved" and app.tech_spec_id:
        ts_result = await db.execute(
            select(TechSpec).where(TechSpec.id == app.tech_spec_id)
        )
        ts = ts_result.scalar_one_or_none()
        if ts and ts.status == "in_pairing":
            ts.status = "assigned"
            await db.commit()

        if ts and ts.product_owner_id:
            await create_notification(
                db, ts.product_owner_id,
                "Team selected for your tech spec",
                f"A team has been selected for '{ts.title}'.",
                "team_selected",
                "tech_spec", str(ts.id),
            )

    await write_audit_log(
        db,
        current_user.id,
        "application.status_changed",
        "application",
        str(app.id),
        {"old_status": old_status, "new_status": body.status},
        ip_address=get_client_ip(request),
    )

    # Email applicant
    user_result = await db.execute(select(User).where(User.id == app.applicant_id))
    applicant = user_result.scalar_one_or_none()
    if applicant:
        background_tasks.add_task(send_status_change, applicant.email, body.status)

    if body.status == "revision_requested":
        await create_notification(
            db, app.applicant_id,
            "Revision requested",
            "Your application requires revisions. Please update and resubmit.",
            "revision_requested",
            "application", str(app.id),
        )
    else:
        await create_notification(
            db, app.applicant_id,
            f"Status changed to {body.status}",
            f"Your application status is now: {body.status}",
            "status_changed",
            "application", str(app.id),
        )

    return app


@router.get("/{application_id}/history")
async def get_application_history(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the full status change history for an application.

    Returns a list of status transitions ordered by ``changed_at``
    descending (most recent first). Each entry includes the old status,
    new status, who made the change, an optional comment, and the timestamp.

    **Access control**: same as ``GET /{application_id}``
    """
    app = await _get_app(application_id, db)
    allowed = ("nti_admin", "evaluator", "mentor")
    if current_user.role not in allowed and app.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    result = await db.execute(
        select(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == application_id)
        .order_by(ApplicationStatusHistory.changed_at.desc())
    )
    history = result.scalars().all()
    return {
        "items": [ApplicationStatusHistoryOut.model_validate(h) for h in history],
        "total": len(history),
    }


# ── Comments ──


@router.get("/{application_id}/comments")
async def list_application_comments(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = await _get_app(application_id, db)

    is_admin = current_user.role in ("nti_admin", "evaluator", "mentor")
    is_owner = app.applicant_id == current_user.id and current_user.role in ("student", "team_leader")

    if not is_admin and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    result = await db.execute(
        select(ApplicationComment)
        .where(ApplicationComment.application_id == application_id)
        .order_by(ApplicationComment.created_at)
    )
    comments = result.scalars().all()

    items = []
    for c in comments:
        if not is_admin and c.is_internal:
            continue
        user_result = await db.execute(select(User).where(User.id == c.user_id))
        comment_user = user_result.scalar_one_or_none()
        items.append(
            ApplicationCommentOut(
                id=c.id,
                application_id=c.application_id,
                user_id=c.user_id,
                user_name=comment_user.full_name if comment_user else "Unknown",
                body=c.body,
                is_internal=c.is_internal,
                created_at=c.created_at,
            )
        )

    return {"items": items}


@router.post(
    "/{application_id}/comments",
    response_model=ApplicationCommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_application_comment(
    request: Request,
    application_id: uuid.UUID,
    body: ApplicationCommentCreate,
    current_user: User = Depends(require_role("nti_admin", "evaluator")),
    db: AsyncSession = Depends(get_db),
):
    app = await _get_app(application_id, db)

    comment = ApplicationComment(
        application_id=application_id,
        user_id=current_user.id,
        body=body.body,
        is_internal=body.is_internal,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    await write_audit_log(
        db,
        current_user.id,
        "application.comment_added",
        "application",
        str(application_id),
        {"comment_id": str(comment.id)},
        ip_address=get_client_ip(request),
    )

    await create_notification(
        db, app.applicant_id,
        "New comment",
        "A new comment has been added to your application.",
        "comment_added",
        "application", str(application_id),
    )

    return ApplicationCommentOut(
        id=comment.id,
        application_id=comment.application_id,
        user_id=comment.user_id,
        user_name=current_user.full_name,
        body=comment.body,
        is_internal=comment.is_internal,
        created_at=comment.created_at,
    )
