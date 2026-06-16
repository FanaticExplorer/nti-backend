"""
Programs router — NTI program type definitions.

Endpoints:
- **List**: public, paginated listing of all programs
- **Get**: retrieve a single program by ID
- **Create**: ``nti_admin`` or ``super_admin`` defines a new program type
- **Update**: ``nti_admin`` or ``super_admin`` modifies an existing program

Programs define the structure and rules for different tracks (e.g.
Program A for team-based incubation, Program B for individual pre-incubation).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.program import Program
from app.models.user import User
from app.schemas.program import ProgramCreate, ProgramOut, ProgramUpdate

router = APIRouter(prefix="/programs", tags=["programs"])


@router.get("")
async def list_programs(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """
    Return a paginated list of all programs.

    **Access**: public
    """
    result = await db.execute(select(Program).offset(skip).limit(limit))
    programs = result.scalars().all()
    total_result = await db.execute(select(func.count(Program.id)))
    total = total_result.scalar_one()
    return {
        "items": [ProgramOut.model_validate(p) for p in programs],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{program_id}", response_model=ProgramOut)
async def get_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a single program by ID.

    Returns 404 if not found.

    **Access**: public
    """
    result = await db.execute(select(Program).where(Program.id == program_id))
    program = result.scalar_one_or_none()
    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Program not found"
        )
    return program


@router.post("", response_model=ProgramOut, status_code=status.HTTP_201_CREATED)
async def create_program(
    body: ProgramCreate,
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new program definition.

    **Access**: ``nti_admin``, ``super_admin``
    """
    program = Program(**body.model_dump())
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program


@router.put("/{program_id}", response_model=ProgramOut)
async def update_program(
    program_id: uuid.UUID,
    body: ProgramUpdate,
    current_user: User = Depends(require_role("nti_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing program definition.

    Only fields present in the request body are updated (partial update).
    Returns 404 if the program does not exist.

    **Access**: ``nti_admin``, ``super_admin``
    """
    result = await db.execute(select(Program).where(Program.id == program_id))
    program = result.scalar_one_or_none()
    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Program not found"
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(program, key, value)
    await db.commit()
    await db.refresh(program)
    return program
