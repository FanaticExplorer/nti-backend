"""
Users router — administrative user management.

Endpoints:
- **List**: paginated listing of all users, optionally filtered by role
- **Get**: retrieve a single user by ID
- **Change role**: ``super_admin`` updates a user's role; writes audit log
- **Deactivate**: soft-deactivate a user (sets ``is_active`` to ``False``)

All endpoints require ``nti_admin`` or ``super_admin`` role (role change
requires ``super_admin`` specifically).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.application import Application
from app.models.application_comment import ApplicationComment
from app.models.notification import Notification
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.user import UserListOut, UserUpdateRole
from app.services.audit_service import get_client_ip, write_audit_log

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role: str | None = Query(None),
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a paginated list of users, optionally filtered by role.

    **Access**: ``nti_admin``, ``super_admin``
    """
    query = select(User).offset(skip).limit(limit)
    if role:
        query = query.where(User.role == role)

    result = await db.execute(query)
    users = result.scalars().all()

    count_query = select(func.count(User.id))
    if role:
        count_query = count_query.where(User.role == role)
    total = (await db.execute(count_query)).scalar_one()

    return {
        "items": [UserListOut.model_validate(u) for u in users],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a single user by ID.

    Returns 404 if the user does not exist.

    **Access**: ``nti_admin``, ``super_admin``
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserListOut.model_validate(user)


@router.patch("/{user_id}/role")
async def change_user_role(
    request: Request,
    user_id: uuid.UUID,
    body: UserUpdateRole,
    current_user: User = Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Change a user's role.

    Writes an audit log entry recording the old and new roles.

    **Access**: ``super_admin`` only
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    old_role = user.role
    user.role = body.role
    await db.commit()

    await write_audit_log(
        db,
        current_user.id,
        "user.role_changed",
        "user",
        str(user.id),
        {"old_role": old_role, "new_role": body.role},
        ip_address=get_client_ip(request),
    )

    return UserListOut.model_validate(user)


@router.patch("/{user_id}/deactivate")
async def deactivate_user(
    request: Request,
    user_id: uuid.UUID,
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivate a user account.

    Sets ``is_active`` to ``False`` (soft deactivation — the user record
    is preserved but login is blocked). Writes an audit log entry.

    **Access**: ``nti_admin``, ``super_admin``
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user.is_active = False
    await db.commit()

    await write_audit_log(
        db,
        current_user.id,
        "user.deactivated",
        "user",
        str(user.id),
        ip_address=get_client_ip(request),
    )

    return UserListOut.model_validate(user)


@router.get("/me/export")
async def export_my_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.student_profile),
            selectinload(User.organizations),
        )
        .where(User.id == current_user.id)
    )
    user = result.scalar_one()

    apps_result = await db.execute(
        select(Application).where(Application.applicant_id == current_user.id)
    )
    applications = apps_result.scalars().all()

    notifs_result = await db.execute(
        select(Notification).where(Notification.user_id == current_user.id)
    )
    notifications = notifs_result.scalars().all()

    return {
        "user": UserOut.model_validate(user).model_dump(),
        "student_profile": (
            {
                "university": user.student_profile.university,
                "study_program": user.student_profile.study_program,
                "year_of_study": user.student_profile.year_of_study,
                "bio": user.student_profile.bio,
            }
            if user.student_profile
            else None
        ),
        "applications": [
            {
                "id": str(a.id),
                "status": a.status,
                "call_id": str(a.call_id),
                "form_data": a.form_data,
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in applications
        ],
        "organizations": [
            {"id": str(o.id), "name": o.name} for o in user.organizations
        ],
        "notifications": [
            {
                "id": str(n.id),
                "title": n.title,
                "body": n.body,
                "action_type": n.action_type,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in notifications
        ],
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


@router.delete("/me")
async def anonymize_my_account(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = current_user

    apps_result = await db.execute(
        select(Application).where(Application.applicant_id == user.id)
    )
    for app in apps_result.scalars().all():
        app.form_data = {}

    comments_result = await db.execute(
        select(ApplicationComment).where(ApplicationComment.user_id == user.id)
    )
    for c in comments_result.scalars().all():
        c.body = "[anonymized]"

    profile_result = await db.execute(
        select(StudentProfile).where(StudentProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile:
        profile.bio = None
        profile.skills = None

    user.email = f"anonymized_{user.id}@deleted.nti.sk"
    user.full_name = "Deleted User"
    user.hashed_password = ""
    user.is_active = False

    await write_audit_log(
        db,
        user.id,
        "user.anonymized",
        "user",
        str(user.id),
        ip_address=get_client_ip(request),
    )

    await db.commit()

    return {"detail": "Account anonymized"}
