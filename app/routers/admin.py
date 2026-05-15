"""
Admin router — dashboard statistics, audit log, and data exports.

Provides administrative endpoints for the NTI platform:
- Aggregated dashboard stats (applications, users, calls, programs, etc.)
- Audit log retrieval with filtering by action, user, and date range
- CSV export of applications (optionally filtered by call)

All endpoints require ``nti_admin`` or ``super_admin`` role unless noted otherwise.
"""

import csv
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.call import Call
from app.models.organization import Organization
from app.models.program import Program
from app.models.team import Team
from app.models.user import User
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def get_dashboard_stats(
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return aggregated platform statistics for the admin dashboard.

    Returns counts for:
    - Applications grouped by status, plus total
    - Users grouped by role, plus total and active count
    - Open and total calls for proposals
    - Total and active programs
    - Total teams
    - Total and approved organizations

    **Access**: ``nti_admin``, ``super_admin``
    """
    # Applications by status
    app_status_query = await db.execute(
        select(Application.status, func.count(Application.id)).group_by(
            Application.status
        )
    )
    apps_by_status = {row[0]: row[1] for row in app_status_query.all()}

    # Users by role
    user_role_query = await db.execute(
        select(User.role, func.count(User.id)).group_by(User.role)
    )
    users_by_role = {row[0]: row[1] for row in user_role_query.all()}

    # Active users count
    active_users_result = await db.execute(
        select(func.count(User.id)).where(User.is_active)
    )
    active_users = active_users_result.scalar()

    # Total users
    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar()

    # Open calls
    open_calls_result = await db.execute(
        select(func.count(Call.id)).where(Call.status == "open")
    )
    open_calls = open_calls_result.scalar()

    # Total calls
    total_calls_result = await db.execute(select(func.count(Call.id)))
    total_calls = total_calls_result.scalar()

    # Total programs
    total_programs_result = await db.execute(select(func.count(Program.id)))
    total_programs = total_programs_result.scalar()

    # Active programs
    active_programs_result = await db.execute(
        select(func.count(Program.id)).where(Program.is_active)
    )
    active_programs = active_programs_result.scalar()

    # Total teams
    total_teams_result = await db.execute(select(func.count(Team.id)))
    total_teams = total_teams_result.scalar()

    # Total organizations
    total_orgs_result = await db.execute(select(func.count(Organization.id)))
    total_orgs = total_orgs_result.scalar()

    # Approved organizations
    approved_orgs_result = await db.execute(
        select(func.count(Organization.id)).where(Organization.is_approved)
    )
    approved_orgs = approved_orgs_result.scalar()

    # Total applications
    total_apps_result = await db.execute(select(func.count(Application.id)))
    total_apps = total_apps_result.scalar()

    return {
        "applications_by_status": apps_by_status,
        "total_applications": total_apps,
        "users_by_role": users_by_role,
        "total_users": total_users,
        "active_users": active_users,
        "open_calls": open_calls,
        "total_calls": total_calls,
        "total_programs": total_programs,
        "active_programs": active_programs,
        "total_teams": total_teams,
        "total_organizations": total_orgs,
        "approved_organizations": approved_orgs,
    }


@router.get("/audit-log")
async def get_audit_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    action: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    current_user: User = Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve paginated audit log entries with optional filters.

    Supports filtering by:
    - **action**: specific audit action type (e.g. ``user.role_changed``)
    - **user_id**: UUID of the user who performed the action
    - **date_from** / **date_to**: ISO 8601 datetime range

    Results are ordered by ``created_at`` descending (newest first).

    **Access**: ``super_admin`` only
    """
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
        count_query = count_query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)
        count_query = count_query.where(AuditLog.created_at <= date_to)

    query = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    return {
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "created_at": log.created_at,
            }
            for log in logs
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/export/applications")
async def export_applications_csv(
    call_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Export applications as a downloadable CSV file.

    Optionally filter by **call_id** to export applications for a specific call.
    The response is a ``StreamingResponse`` with ``Content-Disposition`` header
    set to trigger a file download.

    An audit log entry is written each time an export is triggered.

    **Access**: ``nti_admin``, ``super_admin``
    """
    query = select(Application)
    if call_id:
        query = query.where(Application.call_id == call_id)
    query = query.order_by(Application.created_at.desc())

    result = await db.execute(query)
    apps = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow(
        [
            "id",
            "call_id",
            "team_id",
            "applicant_id",
            "status",
            "is_draft",
            "submitted_at",
            "created_at",
            "updated_at",
        ]
    )

    # Data rows
    for app in apps:
        writer.writerow(
            [
                str(app.id),
                str(app.call_id),
                str(app.team_id) if app.team_id else "",
                str(app.applicant_id),
                app.status,
                app.is_draft,
                app.submitted_at.isoformat() if app.submitted_at else "",
                app.created_at.isoformat() if app.created_at else "",
                app.updated_at.isoformat() if app.updated_at else "",
            ]
        )

    output.seek(0)
    filename = f"applications_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    # Audit
    await write_audit_log(
        db,
        current_user.id,
        "export.triggered",
        "application",
        "csv_export",
        {"call_id": str(call_id) if call_id else None, "count": len(apps)},
    )

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
