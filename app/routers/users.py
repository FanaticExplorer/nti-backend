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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User
from app.schemas.user import UserListOut, UserUpdateRole
from app.services.audit_service import write_audit_log

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

    count_query = select(User)
    if role:
        count_query = count_query.where(User.role == role)
    total = (await db.execute(count_query)).scalars().all()

    return {
        "items": [UserListOut.model_validate(u) for u in users],
        "total": len(total),
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
    )

    return UserListOut.model_validate(user)


@router.patch("/{user_id}/deactivate")
async def deactivate_user(
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
    )

    return UserListOut.model_validate(user)
