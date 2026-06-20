import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.routers import (
    admin,
    applications,
    auth,
    calls,
    content,
    documents,
    evaluations,
    mentorships,
    milestones,
    organizations,
    programs,
    student_profiles,
    teams,
    tech_specs,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    yield
    # Shutdown


app = FastAPI(
    title="NTI Backend",
    description="""
Backend API for the NTI educational platform, managing two programme tracks:
grant incubation (Program A) and live practice placements (Program B).

Covers the full application lifecycle — from registration and submission through
evaluation, onboarding, and project tracking — with JWT-based authentication,
8 role-based access levels, an audit trail for all sensitive operations, and
async email notifications. Every endpoint includes a detailed description in
the OpenAPI docs below.
""",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting via slowapi
app.state.limiter = auth.limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Include all routers
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(student_profiles.router)
app.include_router(organizations.router)
app.include_router(teams.router)
app.include_router(programs.router)
app.include_router(calls.router)
app.include_router(applications.router)
app.include_router(documents.router)
app.include_router(evaluations.router)
app.include_router(mentorships.router)
app.include_router(milestones.router)
app.include_router(content.router)
app.include_router(tech_specs.router)
