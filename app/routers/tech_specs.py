import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.application import Application
from app.models.call import Call
from app.models.organization import Organization, org_members
from app.models.program import Program
from app.models.tech_spec import TechSpec
from app.models.user import User
from app.schemas.tech_spec import (
    TechSpecCreate,
    TechSpecDetailOut,
    TechSpecOut,
    TechSpecStatusUpdate,
    TechSpecUpdate,
)
from app.services.audit_service import get_client_ip, write_audit_log

router = APIRouter(prefix="/tech-specs", tags=["tech-specs"])

VALID_TRANSITIONS = {
    "draft": ["published"],
    "published": ["in_pairing"],
    "in_pairing": ["assigned", "published"],
    "assigned": ["in_realization"],
    "in_realization": ["closed"],
    "closed": [],
}


async def _get_firm_org(current_user: User, db: AsyncSession) -> Organization:
    result = await db.execute(
        select(Organization)
        .join(org_members, org_members.c.organization_id == Organization.id)
        .where(
            org_members.c.user_id == current_user.id,
            org_members.c.role_in_org == "owner",
        )
        .limit(1)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization found for your account",
        )
    return org


async def _firm_owns_tech_spec(
    current_user: User, db: AsyncSession, tech_spec_id: uuid.UUID
) -> bool:
    org = await _get_firm_org(current_user, db)
    result = await db.execute(
        select(TechSpec).where(
            TechSpec.id == tech_spec_id,
            TechSpec.organization_id == org.id,
        )
    )
    return result.scalar_one_or_none() is not None


@router.post("", response_model=TechSpecOut, status_code=status.HTTP_201_CREATED)
async def create_tech_spec(
    body: TechSpecCreate,
    current_user: User = Depends(require_role("firm")),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_firm_org(current_user, db)

    call_result = await db.execute(select(Call).where(Call.id == body.call_id))
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
            detail="Tech specs can only be created for Program B calls",
        )

    ts = TechSpec(
        organization_id=org.id,
        call_id=body.call_id,
        title=body.title,
        description=body.description,
        budget=body.budget,
        product_owner_id=body.product_owner_id,
    )
    db.add(ts)
    await db.commit()
    await db.refresh(ts)
    return ts


@router.get("")
async def list_tech_specs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    organization_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role in ("nti_admin", "super_admin", "mentor", "evaluator"):
        query = select(TechSpec)
    elif current_user.role == "firm":
        org = await _get_firm_org(current_user, db)
        query = select(TechSpec).where(TechSpec.organization_id == org.id)
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    if status_filter:
        query = query.where(TechSpec.status == status_filter)
    if organization_id and current_user.role in ("nti_admin", "super_admin"):
        query = query.where(TechSpec.organization_id == organization_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(query.offset(skip).limit(limit))
    specs = result.scalars().all()

    return {
        "items": [TechSpecOut.model_validate(s) for s in specs],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/backlog")
async def list_backlog(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TechSpec)
        .options(selectinload(TechSpec.organization))
        .where(TechSpec.status.in_(["published", "in_pairing"]))
        .offset(skip)
        .limit(limit)
    )
    specs = result.scalars().all()

    count_result = await db.execute(
        select(func.count(TechSpec.id)).where(
            TechSpec.status.in_(["published", "in_pairing"])
        )
    )
    total = count_result.scalar_one()

    items = []
    for s in specs:
        items.append(
            TechSpecDetailOut(
                id=s.id,
                organization_id=s.organization_id,
                call_id=s.call_id,
                product_owner_id=s.product_owner_id,
                title=s.title,
                description=s.description,
                budget=s.budget,
                status=s.status,
                created_at=s.created_at,
                updated_at=s.updated_at,
                organization_name=s.organization.name if s.organization else None,
            )
        )

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/{tech_spec_id}")
async def get_tech_spec(
    tech_spec_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed_roles = ("nti_admin", "super_admin", "mentor", "evaluator", "firm")
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    query = select(TechSpec).options(
        selectinload(TechSpec.organization),
        selectinload(TechSpec.product_owner),
    )

    if current_user.role == "firm":
        org = await _get_firm_org(current_user, db)
        query = query.where(
            TechSpec.id == tech_spec_id,
            TechSpec.organization_id == org.id,
        )
    else:
        query = query.where(TechSpec.id == tech_spec_id)

    result = await db.execute(query)
    ts = result.scalar_one_or_none()
    if not ts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tech spec not found"
        )

    app_count_result = await db.execute(
        select(func.count(Application.id)).where(
            Application.tech_spec_id == ts.id
        )
    )
    app_count = app_count_result.scalar_one()

    return TechSpecDetailOut(
        id=ts.id,
        organization_id=ts.organization_id,
        call_id=ts.call_id,
        product_owner_id=ts.product_owner_id,
        title=ts.title,
        description=ts.description,
        budget=ts.budget,
        status=ts.status,
        created_at=ts.created_at,
        updated_at=ts.updated_at,
        organization_name=ts.organization.name if ts.organization else None,
        product_owner_name=ts.product_owner.full_name if ts.product_owner else None,
        application_count=app_count,
    )


@router.patch("/{tech_spec_id}", response_model=TechSpecOut)
async def update_tech_spec(
    tech_spec_id: uuid.UUID,
    body: TechSpecUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("firm", "nti_admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    if current_user.role == "firm":
        if not await _firm_owns_tech_spec(current_user, db, tech_spec_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Tech spec not found"
            )

    result = await db.execute(select(TechSpec).where(TechSpec.id == tech_spec_id))
    ts = result.scalar_one_or_none()
    if not ts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tech spec not found"
        )

    if ts.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only draft tech specs can be updated",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ts, key, value)
    await db.commit()
    await db.refresh(ts)
    return ts


@router.patch("/{tech_spec_id}/status", response_model=TechSpecOut)
async def change_tech_spec_status(
    request: Request,
    tech_spec_id: uuid.UUID,
    body: TechSpecStatusUpdate,
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TechSpec).where(TechSpec.id == tech_spec_id))
    ts = result.scalar_one_or_none()
    if not ts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tech spec not found"
        )

    allowed = VALID_TRANSITIONS.get(ts.status, [])
    if body.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Cannot transition from '{ts.status}' to '{body.status}'. Allowed: {allowed}",
        )

    old_status = ts.status
    ts.status = body.status
    await db.commit()
    await db.refresh(ts)

    await write_audit_log(
        db,
        current_user.id,
        "tech_spec.status_changed",
        "tech_spec",
        str(ts.id),
        {"old_status": old_status, "new_status": body.status},
        ip_address=get_client_ip(request),
    )

    return ts


@router.delete("/{tech_spec_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tech_spec(
    tech_spec_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("firm", "nti_admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    if current_user.role == "firm":
        if not await _firm_owns_tech_spec(current_user, db, tech_spec_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Tech spec not found"
            )

    result = await db.execute(select(TechSpec).where(TechSpec.id == tech_spec_id))
    ts = result.scalar_one_or_none()
    if not ts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tech spec not found"
        )

    if ts.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only draft tech specs can be deleted",
        )

    app_count = await db.execute(
        select(func.count(Application.id)).where(Application.tech_spec_id == ts.id)
    )
    if app_count.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot delete tech spec with linked applications",
        )

    await db.delete(ts)
    await db.commit()
