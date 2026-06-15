"""
Organizations router — partner (firm) organization management.

Endpoints:
- **Create**: ``firm`` users register their organization; creator is
  automatically added as an ``owner`` member
- **List**: admins list all organizations (paginated)
- **Get**: retrieve a single organization (firm users can only see their own)
- **Approve**: ``nti_admin`` / ``super_admin`` approve an organization;
  triggers a notification email
- **Add member**: organization owner can add other users as members
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.organization import Organization, org_members
from app.models.user import User
from app.schemas.organization import (
    AddMemberRequest,
    OrganizationCreate,
    OrganizationOut,
)
from app.services.audit_service import write_audit_log
from app.utils.email import send_organization_approved

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate,
    current_user: User = Depends(require_role("firm")),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new organization.

    The authenticated ``firm`` user becomes the first member with the
    ``owner`` role in the organization.

    **Access**: ``firm`` only
    """
    org = Organization(**body.model_dump())
    db.add(org)
    await db.commit()
    await db.refresh(org)

    # Add creator as member
    stmt = org_members.insert().values(
        user_id=current_user.id,
        organization_id=org.id,
        role_in_org="owner",
    )
    await db.execute(stmt)
    await db.commit()

    return org


@router.get("")
async def list_organizations(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a paginated list of all organizations.

    **Access**: ``nti_admin``, ``super_admin``
    """
    result = await db.execute(select(Organization).offset(skip).limit(limit))
    orgs = result.scalars().all()
    total_result = await db.execute(select(Organization))
    total = len(total_result.scalars().all())

    return {
        "items": [OrganizationOut.model_validate(o) for o in orgs],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a single organization by ID.

    **Access control**:
    - ``firm`` users can only see organizations they belong to
    - ``nti_admin`` and ``mentor`` can see any organization
    - Other roles receive a 403
    """
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Access control: firm users can only see their own org, nti_admin/mentor/super_admin can see all
    if current_user.role == "firm":
        member_check = await db.execute(
            select(org_members).where(
                org_members.c.user_id == current_user.id,
                org_members.c.organization_id == org_id,
            )
        )
        if not member_check.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )
    elif current_user.role not in ("nti_admin", "super_admin", "mentor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    return org


@router.patch("/{org_id}/approve")
async def approve_organization(
    org_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve an organization.

    Sets ``is_approved`` to ``True``, writes an audit log entry, and
    queues an approval notification email to the organization's contact.

    **Access**: ``nti_admin``, ``super_admin``
    """
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    org.is_approved = True
    await db.commit()

    await write_audit_log(
        db,
        current_user.id,
        "organization.approved",
        "organization",
        str(org.id),
    )

    background_tasks.add_task(send_organization_approved, org.contact_email)

    return {"detail": "Organization approved"}


@router.post("/{org_id}/members")
async def add_member(
    org_id: uuid.UUID,
    body: AddMemberRequest,
    current_user: User = Depends(require_role("firm")),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a user as a member of an organization.

    Only the organization ``owner`` can add new members. The new member's
    role within the organization is specified in the request body.

    **Access**: ``firm`` (must be the organization owner)
    """
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check if user is the organization owner
    member_check = await db.execute(
        select(org_members).where(
            org_members.c.user_id == current_user.id,
            org_members.c.organization_id == org_id,
            org_members.c.role_in_org == "owner",
        )
    )
    if not member_check.first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owner can add members",
        )

    stmt = org_members.insert().values(
        user_id=body.user_id,
        organization_id=org_id,
        role_in_org=body.role_in_org,
    )
    await db.execute(stmt)
    await db.commit()

    return {"detail": "Member added"}
