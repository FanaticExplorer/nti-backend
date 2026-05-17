"""
Test fixtures and configuration for the NTI Backend test suite.

Uses an in-memory SQLite database (via aiosqlite) for fast, isolated tests.
PostgreSQL-specific column types (UUID, JSON, Enum) are automatically converted
to SQLite-compatible types via direct type replacement on the metadata.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import sqltypes
from sqlalchemy.types import TypeDecorator

from app.database import Base, get_db
from app.main import app
from app.models.application import Application
from app.models.call import Call
from app.models.organization import Organization, org_members
from app.models.program import Program
from app.models.team import Team, team_members
from app.models.user import User
from app.utils.security import create_access_token, hash_password

# ── Prevent real email sending in tests ───────────────────────────────────

_patch_email = patch("app.utils.email._send", new_callable=AsyncMock)
_patch_email.start()

# ── PostgreSQL → SQLite type conversion ───────────────────────────────────


class UUIDAsStr(TypeDecorator):
    """Store UUIDs as strings — keeps SQLite happy while round-tripping uuid.UUID."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return uuid.UUID(value) if value is not None else None


def _patch_pg_types_for_sqlite():
    """Walk all columns in Base.metadata and swap PG types for SQLite equivalents."""
    from sqlalchemy.dialects.postgresql import JSON as PGJSON
    from sqlalchemy.dialects.postgresql import UUID as PGUUID

    # Force import of all model modules so tables are registered in metadata
    import app.models.application  # noqa: F401
    import app.models.application_status_history  # noqa: F401
    import app.models.audit_log  # noqa: F401
    import app.models.call  # noqa: F401
    import app.models.content  # noqa: F401
    import app.models.document  # noqa: F401
    import app.models.evaluation  # noqa: F401
    import app.models.mentorship  # noqa: F401
    import app.models.mentorship_log  # noqa: F401
    import app.models.milestone  # noqa: F401
    import app.models.organization  # noqa: F401
    import app.models.program  # noqa: F401
    import app.models.student_profile  # noqa: F401
    import app.models.team  # noqa: F401
    import app.models.user  # noqa: F401

    for table in list(Base.metadata.tables.values()):
        for col in table.columns:
            t = col.type
            if isinstance(t, PGUUID):
                col.type = UUIDAsStr()
            elif isinstance(t, PGJSON):
                col.type = sqltypes.JSON()
            elif isinstance(t, sqltypes.Enum):
                col.type = String(50)


# ── Engine & session factory ──────────────────────────────────────────────

DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

_connect_args: dict = {}
if "sqlite" in DB_URL:
    _connect_args = {"check_same_thread": False}
    _patch_pg_types_for_sqlite()

_test_engine = create_async_engine(
    DB_URL,
    echo=False,
    connect_args=_connect_args,
    poolclass=StaticPool,
)

_TestSessionFactory = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session")
def _engine_ready():
    """Create all tables once per test session."""

    async def _init():
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(_init())


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
async def db(_engine_ready) -> AsyncGenerator[AsyncSession, None]:
    """Async DB session — rolled back after each test."""
    async with _test_engine.connect() as conn:
        await conn.begin()
        session = _TestSessionFactory(bind=conn)
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


@pytest.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client with DB dependency override."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def pytest_sessionfinish(session, exitstatus):
    """Stop the email patch when the test session ends."""
    _patch_email.stop()


def auth_headers(user: User) -> dict[str, str]:
    """Return ``Authorization: Bearer <token>`` for *user*."""
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


# ── Factory fixtures ──────────────────────────────────────────────────────


@pytest.fixture
async def user_factory(db: AsyncSession) -> Callable[..., Awaitable[User]]:
    """Create a User with sensible defaults.  ``await user_factory(role='student')``"""

    async def _create(
        role: str = "student",
        email: str | None = None,
        full_name: str = "Test User",
        is_active: bool = True,
        is_email_verified: bool = True,
        **kwargs: Any,
    ) -> User:
        email = email or f"{role}_{uuid.uuid4().hex[:8]}@test.com"
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hash_password("testpass123"),
            full_name=full_name,
            role=role,
            is_active=is_active,
            is_email_verified=is_email_verified,
            gdpr_consent=True,
            gdpr_consent_at=datetime.now(timezone.utc),
            **kwargs,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    return _create


@pytest.fixture
async def student(db: AsyncSession, user_factory) -> User:
    """Convenience: a persisted student user."""
    return await user_factory(role="student")


@pytest.fixture
async def team_leader(db: AsyncSession, user_factory) -> User:
    """Convenience: a persisted team_leader user."""
    return await user_factory(role="team_leader")


@pytest.fixture
async def firm_user(db: AsyncSession, user_factory) -> User:
    """Convenience: a persisted firm user."""
    return await user_factory(role="firm")


@pytest.fixture
async def mentor(db: AsyncSession, user_factory) -> User:
    """Convenience: a persisted mentor user."""
    return await user_factory(role="mentor")


@pytest.fixture
async def evaluator(db: AsyncSession, user_factory) -> User:
    """Convenience: a persisted evaluator user."""
    return await user_factory(role="evaluator")


@pytest.fixture
async def nti_admin(db: AsyncSession, user_factory) -> User:
    """Convenience: a persisted nti_admin user."""
    return await user_factory(role="nti_admin")


@pytest.fixture
async def super_admin(db: AsyncSession, user_factory) -> User:
    """Convenience: a persisted super_admin user."""
    return await user_factory(role="super_admin")


@pytest.fixture
async def content_editor(db: AsyncSession, user_factory) -> User:
    """Convenience: a persisted content_editor user."""
    return await user_factory(role="content_editor")


# ── Higher-level domain fixtures ──────────────────────────────────────────


@pytest.fixture
async def program(db: AsyncSession) -> Program:
    """A default active Program A."""
    p = Program(
        id=uuid.uuid4(),
        title="Test Program A",
        type="A",
        description="A test incubation program",
        is_active=True,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@pytest.fixture
async def program_b(db: AsyncSession) -> Program:
    """A default active Program B."""
    p = Program(
        id=uuid.uuid4(),
        title="Test Program B",
        type="B",
        description="A test pre-incubation program",
        is_active=True,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@pytest.fixture
async def organization(db: AsyncSession, firm_user: User) -> Organization:
    """An approved organization with *firm_user* as owner."""
    org = Organization(
        id=uuid.uuid4(),
        name="TestOrg s.r.o.",
        ico="12345678",
        contact_email=firm_user.email,
        is_approved=True,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)

    stmt = org_members.insert().values(
        user_id=firm_user.id, organization_id=org.id, role_in_org="owner"
    )
    await db.execute(stmt)
    await db.commit()
    return org


@pytest.fixture
async def call(db: AsyncSession, program: Program, nti_admin: User) -> Call:
    """An open call for *program*."""
    c = Call(
        id=uuid.uuid4(),
        program_id=program.id,
        title="Test Call",
        description="A test call for proposals",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc),
        status="open",
        created_by=nti_admin.id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@pytest.fixture
async def team(db: AsyncSession, team_leader: User, student: User) -> Team:
    """A team of 2 members led by *team_leader*."""
    t = Team(
        id=uuid.uuid4(),
        name="Test Team",
        leader_id=team_leader.id,
        program_type="A",
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)

    for uid in (team_leader.id, student.id):
        await db.execute(team_members.insert().values(team_id=t.id, user_id=uid))
    await db.commit()
    return t


@pytest.fixture
async def application(
    db: AsyncSession, call: Call, student: User, team: Team
) -> Application:
    """A draft application for *call* by *student* with *team*."""
    app = Application(
        id=uuid.uuid4(),
        call_id=call.id,
        team_id=team.id,
        applicant_id=student.id,
        form_data={"project_name": "Test Project"},
        status="draft",
        is_draft=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app
