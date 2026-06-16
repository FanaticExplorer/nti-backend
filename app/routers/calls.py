"""
Calls router — management of calls for proposals.

Endpoints cover:
- Public listing of calls (defaults to ``open`` status)
- Retrieving a single call
- Creating calls (``nti_admin``, ``super_admin``, or ``firm`` users)
- Updating call details (owner or admin)
- Changing call status (admin only)

Firm users can only create calls for organizations they belong to and
can only update their own calls.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.call import Call
from app.models.organization import org_members
from app.models.user import User
from app.schemas.call import CallCreate, CallOut, CallStatusUpdate, CallUpdate

router = APIRouter(prefix="/calls", tags=["calls"])

VALID_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["open"],
    "open": ["matching", "closed"],
    "matching": ["assigned", "closed"],
    "assigned": ["in_progress", "closed"],
    "in_progress": ["closed"],
}


@router.get("")
async def list_calls(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a paginated list of calls.

    Defaults to ``open`` calls if no **status** filter is provided.

    **Access**: public (no authentication required)
    """
    query = select(Call).where(Call.status == (status if status else "open"))
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    calls = result.scalars().all()

    count_query = select(func.count(Call.id)).where(Call.status == (status if status else "open"))
    total = (await db.execute(count_query)).scalar_one()

    return {
        "items": [CallOut.model_validate(c) for c in calls],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{call_id}", response_model=CallOut)
async def get_call(
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a single call by ID.

    Returns 404 if not found.

    **Access**: public (no authentication required)
    """
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
        )
    return call


@router.post("", response_model=CallOut, status_code=status.HTTP_201_CREATED)
async def create_call(
    body: CallCreate,
    current_user: User = Depends(require_role("nti_admin", "super_admin", "firm")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new call for proposals.

    - ``nti_admin`` and ``super_admin`` can create calls without restriction
    - ``firm`` users must provide an ``organization_id`` and must be a
      member of that organization

    The ``created_by`` field is set to the authenticated user's ID.

    **Access**: ``nti_admin``, ``super_admin``, ``firm``
    """
    # Access control: nti_admin, super_admin can always create; firm only if they belong to the org
    if current_user.role == "firm":
        if not body.organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Firm users must provide organization_id",
            )
        # Check if user belongs to this organization
        member_check = await db.execute(
            select(org_members).where(
                org_members.c.user_id == current_user.id,
                org_members.c.organization_id == body.organization_id,
            )
        )
        if not member_check.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this organization",
            )

    call = Call(created_by=current_user.id, **body.model_dump())
    db.add(call)
    await db.commit()
    await db.refresh(call)
    return call


@router.put("/{call_id}", response_model=CallOut)
async def update_call(
    call_id: uuid.UUID,
    body: CallUpdate,
    current_user: User = Depends(require_role("nti_admin", "super_admin", "firm")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing call's details.

    - ``nti_admin`` and ``super_admin`` can update any call
    - ``firm`` users can only update calls they created

    Only fields present in the request body are updated (partial update).

    **Access**: ``nti_admin``, ``super_admin``, or the ``firm`` creator
    """
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
        )

    # Access control: firm users can only update their own calls
    if current_user.role == "firm" and call.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your call"
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(call, key, value)
    await db.commit()
    await db.refresh(call)
    return call


@router.patch("/{call_id}/status", response_model=CallOut)
async def change_call_status(
    call_id: uuid.UUID,
    body: CallStatusUpdate,
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Change the status of a call.

    Validates the transition against ``VALID_TRANSITIONS``. If the
    requested status is not an allowed next step from the current status,
    a 422 error is returned listing the allowed transitions.

    **Access**: ``nti_admin``, ``super_admin``
    """
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
        )

    allowed = VALID_TRANSITIONS.get(call.status, [])
    if body.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Cannot transition from '{call.status}' to '{body.status}'. Allowed: {allowed}",
        )

    call.status = body.status
    await db.commit()
    await db.refresh(call)
    return call
