"""
Teams router — student team management.

Endpoints:
- **Create**: a ``student`` creates a team and is promoted to ``team_leader``
- **My teams**: list teams the current user belongs to
- **Get team**: retrieve team details including the full member list
- **Invite**: team leader adds a user by email
- **Join**: any ``student`` can join an existing team
- **Remove member**: team leader removes a member (cannot remove themselves)

Teams are the basis for Program A (incubation) applications where at
least 3 members with student profiles are required.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.team import Team, team_members
from app.models.user import User
from app.schemas.team import TeamCreate, TeamDetailOut, TeamOut

router = APIRouter(prefix="/teams", tags=["teams"])


def _user_out(user: User) -> dict:
    """
    Serialize a User object to a dict with a safe subset of fields.

    Returns only ``id``, ``email``, ``full_name``, and ``role`` —
    excluding sensitive fields like ``hashed_password``.
    """
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    }


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    current_user: User = Depends(require_role("student")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new team.

    The creating user becomes the team leader and is automatically added
    as a member. If the user's current role is ``student``, it is promoted
    to ``team_leader``.

    **Access**: ``student``
    """
    team = Team(
        name=body.name,
        leader_id=current_user.id,
        program_type=body.program_type,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)

    # Add creator as member + promote to team_leader role
    stmt = team_members.insert().values(team_id=team.id, user_id=current_user.id)
    await db.execute(stmt)

    if current_user.role == "student":
        current_user.role = "team_leader"

    await db.commit()

    return team


@router.get("/my")
async def get_my_teams(
    current_user: User = Depends(require_role("student", "team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return all teams the current user belongs to.

    **Access**: ``student``, ``team_leader``
    """
    result = await db.execute(
        select(Team)
        .join(team_members, Team.id == team_members.c.team_id)
        .where(team_members.c.user_id == current_user.id)
    )
    teams = result.scalars().all()
    return {
        "items": [TeamOut.model_validate(t) for t in teams],
        "total": len(teams),
        "skip": 0,
        "limit": 100,
    }


@router.get("/{team_id}", response_model=TeamDetailOut)
async def get_team(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve team details including the full member list.

    Returns the team metadata plus a ``members`` array with each member's
    id, email, full_name, and role.

    **Access**: any authenticated user
    """
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )

    # Fetch members
    member_result = await db.execute(
        select(User)
        .join(team_members, User.id == team_members.c.user_id)
        .where(team_members.c.team_id == team_id)
    )
    members = member_result.scalars().all()

    team_out = TeamDetailOut.model_validate(team)
    team_out.members = [_user_out(m) for m in members]
    return team_out


@router.post("/{team_id}/invite")
async def invite_member(
    team_id: uuid.UUID,
    email: str,
    current_user: User = Depends(require_role("team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Invite a user to the team by email.

    Only the team leader can invite. The invited user must already exist
    in the system. Returns 409 if the user is already a member.

    **Access**: ``team_leader`` (must be the team's leader)
    """
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )
    if team.leader_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only team leader can invite"
        )

    # Find user by email
    user_result = await db.execute(select(User).where(User.email == email))
    invited = user_result.scalar_one_or_none()
    if not invited:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check if already a member
    existing = await db.execute(
        select(team_members).where(
            team_members.c.team_id == team_id,
            team_members.c.user_id == invited.id,
        )
    )
    if existing.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already a member"
        )

    stmt = team_members.insert().values(team_id=team_id, user_id=invited.id)
    await db.execute(stmt)
    await db.commit()

    return {"detail": "Member invited and added"}


@router.post("/{team_id}/join")
async def join_team(
    team_id: uuid.UUID,
    current_user: User = Depends(require_role("student")),
    db: AsyncSession = Depends(get_db),
):
    """
    Join an existing team.

    Any ``student`` can join any team. Returns 409 if already a member.

    **Access**: ``student``
    """
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )

    existing = await db.execute(
        select(team_members).where(
            team_members.c.team_id == team_id,
            team_members.c.user_id == current_user.id,
        )
    )
    if existing.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already a member"
        )

    stmt = team_members.insert().values(team_id=team_id, user_id=current_user.id)
    await db.execute(stmt)
    await db.commit()

    return {"detail": "Joined team successfully"}


@router.delete("/{team_id}/members/{user_id}")
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(require_role("team_leader")),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove a member from the team.

    Only the team leader can remove members. The leader cannot remove
    themselves. Returns 404 if the specified user is not a member.

    **Access**: ``team_leader`` (must be the team's leader)
    """
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )
    if team.leader_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team leader can remove members",
        )
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself as leader",
        )

    # Check member exists first
    member_check = await db.execute(
        select(team_members).where(
            team_members.c.team_id == team_id,
            team_members.c.user_id == user_id,
        )
    )
    if not member_check.first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    stmt = team_members.delete().where(
        team_members.c.team_id == team_id,
        team_members.c.user_id == user_id,
    )
    await db.execute(stmt)
    await db.commit()

    return {"detail": "Member removed"}
