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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.organization import Organization, org_members
from app.models.user import User
from app.schemas.organization import (
    AddMemberRequest,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
    UpdateMemberRoleRequest,
)
from app.services.audit_service import get_client_ip, write_audit_log
from app.utils.email import send_organization_approved
from app.utils.notifications import create_notification

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
    total_result = await db.execute(select(func.count(Organization.id)))
    total = total_result.scalar() or 0

    return {
        "items": [OrganizationOut.model_validate(o) for o in orgs],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: uuid.UUID,
    current_user: User = Depends(require_role("firm", "nti_admin", "super_admin", "mentor")),
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

    # Access control: firm users can only see their own org
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

    return org


@router.patch("/{org_id}/approve")
async def approve_organization(
    request: Request,
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
        ip_address=get_client_ip(request),
    )

    background_tasks.add_task(send_organization_approved, org.contact_email)

    owner_result = await db.execute(
        select(User).join(org_members, org_members.c.user_id == User.id).where(
            org_members.c.organization_id == org_id,
            org_members.c.role_in_org == "owner",
        ).limit(1)
    )
    owner = owner_result.scalar_one_or_none()
    if owner:
        await create_notification(
            db, owner.id,
            "Organization approved",
            "Your organization has been approved.",
            "organization_approved",
            "organization", str(org.id),
        )

    return {"detail": "Organization approved"}


@router.put("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: uuid.UUID,
    body: OrganizationUpdate,
    current_user: User = Depends(require_role("firm", "nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # firm users can only update their own org
    if current_user.role == "firm":
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
                detail="Only organization owner can edit",
            )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(org, key, value)
    await db.commit()
    await db.refresh(org)
    return org


@router.post("/{org_id}/members")
async def add_member(
    org_id: uuid.UUID,
    body: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    is_admin = current_user.role in ("nti_admin", "super_admin")
    if not is_admin:
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

    existing = await db.execute(
        select(org_members).where(
            org_members.c.user_id == body.user_id,
            org_members.c.organization_id == org_id,
        )
    )
    if existing.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this organization",
        )

    stmt = org_members.insert().values(
        user_id=body.user_id,
        organization_id=org_id,
        role_in_org=body.role_in_org,
    )
    await db.execute(stmt)
    await db.commit()

    return {"detail": "Member added"}


@router.get("/{org_id}/members")
async def list_members(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org = await db.execute(select(Organization).where(Organization.id == org_id))
    if not org.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    result = await db.execute(
        select(org_members.c.user_id, org_members.c.role_in_org, User.full_name, User.email)
        .join(User, User.id == org_members.c.user_id)
        .where(org_members.c.organization_id == org_id)
    )
    members = [
        {"user_id": str(r[0]), "role_in_org": r[1], "full_name": r[2], "email": r[3]}
        for r in result.all()
    ]
    return {"items": members}


@router.patch("/{org_id}/members/{user_id}")
async def update_member_role(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateMemberRoleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_admin = current_user.role in ("nti_admin", "super_admin")
    if not is_admin:
        owner_check = await db.execute(
            select(org_members).where(
                org_members.c.user_id == current_user.id,
                org_members.c.organization_id == org_id,
                org_members.c.role_in_org == "owner",
            )
        )
        if not owner_check.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization owner can change member roles",
            )

    result = await db.execute(
        select(org_members).where(
            org_members.c.user_id == user_id,
            org_members.c.organization_id == org_id,
        )
    )
    if not result.first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this organization",
        )

    stmt = (
        org_members.update()
        .where(
            org_members.c.user_id == user_id,
            org_members.c.organization_id == org_id,
        )
        .values(role_in_org=body.role_in_org)
    )
    await db.execute(stmt)
    await db.commit()

    return {"detail": "Member role updated"}


@router.delete("/{org_id}/members/{user_id}")
async def remove_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_admin = current_user.role in ("nti_admin", "super_admin")
    if not is_admin:
        owner_check = await db.execute(
            select(org_members).where(
                org_members.c.user_id == current_user.id,
                org_members.c.organization_id == org_id,
                org_members.c.role_in_org == "owner",
            )
        )
        if not owner_check.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization owner can remove members",
            )

    member = await db.execute(
        select(org_members).where(
            org_members.c.user_id == user_id,
            org_members.c.organization_id == org_id,
        )
    )
    if not member.first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this organization",
        )

    stmt = org_members.delete().where(
        org_members.c.user_id == user_id,
        org_members.c.organization_id == org_id,
    )
    await db.execute(stmt)
    await db.commit()

    return {"detail": "Member removed"}
