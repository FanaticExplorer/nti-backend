# NTI Backend

The backend API for the NTI platform, built with FastAPI. It supports two core programmes run by the NTI educational institution: a grant incubation track (Program A) and a live practice placement track (Program B). Together these cover the full lifecycle — from application and onboarding through to project tracking and reporting.

## Mapping to Assignment Requirements

![Swagger UI screenshot showing all implemented stuff](/assets/swagger-ui.png)

### Covered Requirements

- **§4 User roles** — 9 roles: `student`, `team_leader`, `firm`, `evaluator`, `mentor`, `nti_admin`, `super_admin`, `content_editor`, `visitor`, enforced via `require_role()` dependency.
- **§6.1 Public web / CMS** — `content` router with CRUD for pages (`/content/pages/{slug}`) and news articles (`/content/news`), each with publish/draft status. Public FAQ (`/content/faq`), contact form (`/content/contact` with rate limiting), sitemap (`/content/sitemap.xml`). SEO meta fields on pages.
- **§6.2 Authentication & onboarding** — Full JWT auth flow: `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/verify-email`, `/auth/forgot-password`, `/auth/reset-password`. Rate limiting on auth endpoints, GDPR consent tracking, and welcome emails.
- **§6.3 Registration forms & workflow** — `applications` router implementing the full cycle: draft → submit → formal verification → evaluation → approval → onboarding → active → completed. Program B uses a separate TechSpec/backlog/pairing flow.
- **§6.4 Notifications** — In-app notification center (`/notifications`): list, unread count, mark read, mark all read. Triggers on registration, application submit/status change, evaluation, mentor assignment, org approval. Background email tasks for welcome, application submitted, status change, and organisation approved events (SMTP via `app/utils/email.py`).
- **§6.5 Dashboards & exports** — `admin/stats` endpoint with aggregation queries; `admin/export/applications` CSV export with streaming response; firm dashboard (`/tech-specs/firm/dashboard`).
- **§7.1 Program A — categories & stacks** — `Program` and `Call` models with a `type` discriminator (`A` / `B`) and thematic categories.
- **§7.3 Program A — mandatory project docs** — Submission validation enforces 6 required documents: Executive Summary, Technical Architecture, Roadmap, Budget plan, Risk analysis, Monetization model (`applications.py` submit logic).
- **§7.4 Program A — statuses & project tracking** — 11 application statuses governed by a validated state machine (`VALID_TRANSITIONS` dict), status history tracking, and milestones with an approval workflow.
- **§8.2 Program B — firm onboarding** — `organizations` router: firm registration, admin approval flow, member management with roles (admin, member, product_owner). `tech_specs` router: firm creates TechSpec → admin publishes → public backlog → student applies → pairing → realization.
- **§8.4 Program B — tracking** — Mentorship assignment, mentorship session logs, per-application milestone tracking, commission comments on applications with public/internal visibility.
- **§10 Data model** — 20 SQLAlchemy models covering all domain entities from the specification.
- **§11.1 Backend modules** — 16 FastAPI routers, a service layer (`audit_service`), and utility modules for email, notifications, and security.
- **§11.2 API principles** — RESTful JSON API, Pydantic request/response validation, pagination (`skip`/`limit`), OpenAPI docs auto-generated at `/docs`.
- **§13 Security & GDPR** — JWT with HS256, password hashing (argon2 via passlib), rate limiting (slowapi), audit log for all sensitive actions, GDPR consent field with timestamp, user data export (`GET /users/me/export`), account anonymization (`DELETE /users/me`), document classification levels (public/internal/confidential).
- **§14 DevOps** — Docker Compose (PostgreSQL + App), Dockerfile, health check endpoint (`/health`), environment-based configuration via `.env`, `uv.lock` for reproducible builds.


### Technology Choices

| Concern | Technology |
|---|---|
| Framework | FastAPI (async) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Auth | JWT (python-jose + passlib[argon2]) |
| Validation | Pydantic v2 |
| Rate limiting | slowapi |
| Email | fastapi-mail |
| Database | PostgreSQL 15+ |
| Containerization | Docker + docker-compose |

## Prerequisites

- Python 3.13+
- PostgreSQL 15+ (or Docker)

## Quick Start (with Docker)

```bash
# 1. Clone and enter the project
cd nti-backend

# 2. Set up environment variables
cp .env.example .env
# Edit .env if needed (defaults work with Docker)

# 3. Start all services (PostgreSQL, App)
docker-compose up -d

# 4. Run database migrations
docker-compose exec app uv run alembic upgrade head

# 5. Access the API
# Swagger UI: http://localhost:8000/docs
# ReDoc:      http://localhost:8000/redoc
```

## Local Development Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env from example
cp .env.example .env
# Edit .env — make sure DATABASE_URL points to your PostgreSQL

# 4. Start PostgreSQL (via Docker or locally)
# Option A: Start only DB with Docker
docker-compose up -d db

# Option B: Use your own PostgreSQL instance
# Update DATABASE_URL in .env accordingly

# 5. Run database migrations
alembic upgrade head

# 6. Start the development server
python main.py
# Or directly:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 7. Open Swagger UI
# http://localhost:8000/docs
```

> **Note:** If you prefer [uv](https://docs.astral.sh/uv/), you can use `uv sync` and `uv run` instead — both a `pyproject.toml` and `uv.lock` are included in the repository.

## Database Migrations

```bash
# Generate a new migration after model changes
alembic revision --autogenerate -m "description"

# Apply pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) | — |
| `JWT_SECRET_KEY` | Secret key for JWT signing | — |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |
| `MAIL_USERNAME` | SMTP username | — |
| `MAIL_PASSWORD` | SMTP password | — |
| `MAIL_FROM` | Sender email address | `nti@example.com` |
| `MAIL_PORT` | SMTP port | `587` |
| `MAIL_SERVER` | SMTP server host | `smtp.gmail.com` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:5173,http://localhost:3000` |
| `MAX_UPLOAD_SIZE_MB` | Max file upload size in MB | `10` |
| `UPLOAD_DIR` | Directory for uploaded files | `uploads` |
| `APP_ENV` | Environment (`development` / `production`) | `development` |

## API Documentation

Once running, interactive API docs are available at:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

Every endpoint includes a detailed description of its purpose, parameters, and
responses — visible directly in the OpenAPI docs.

### Key Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login, get access token |
| GET | `/auth/me` | Get current user profile |
| GET | `/health` | Health check |
| GET | `/users` | List users (admin) |
| GET | `/users/me/export` | Export all personal data (GDPR) |
| DELETE | `/users/me` | Anonymize account (GDPR) |
| GET | `/notifications` | List in-app notifications |
| GET | `/notifications/unread-count` | Unread notification count |
| GET | `/programs` | List programs (public) |
| GET | `/calls` | List calls (public) |
| POST | `/applications` | Create application draft |
| POST | `/applications/{id}/submit` | Submit application |
| GET | `/applications/{id}/comments` | List commission comments |
| POST | `/tech-specs` | Create TechSpec (firm) |
| GET | `/tech-specs/backlog` | Public backlog of open TechSpecs |
| GET | `/tech-specs/firm/dashboard` | Firm dashboard |
| POST | `/content/contact` | Submit contact form message |
| GET | `/content/faq` | List published FAQ |
| GET | `/content/pages/{slug}` | Get public content page |
| GET | `/content/sitemap.xml` | XML sitemap |
| GET | `/admin/stats` | Dashboard statistics (admin) |
| GET | `/admin/export/applications` | Export applications as CSV |

## Structure

```
nti-backend/
├── alembic/             # Database migrations
├── app/
│   ├── models/          # SQLAlchemy models (20 models)
│   ├── routers/         # API route handlers (16 routers)
│   ├── schemas/         # Pydantic request/response schemas
│   ├── services/        # Business logic
│   ├── utils/           # Email, notifications, security helpers
│   ├── config.py        # Pydantic settings
│   ├── database.py      # Async engine & session
│   ├── dependencies.py  # FastAPI dependencies (auth)
│   └── main.py          # FastAPI app entry point
├── tests/               # pytest test suite (161 tests)
├── uploads/             # Uploaded files
├── .env.example         # Environment template
├── docker-compose.yml   # Docker services
├── Dockerfile           # App container
├── pyproject.toml       # Project metadata (uv/poetry compat)
├── requirements.txt     # Pip dependencies
└── uv.lock              # Locked dependency versions (uv)
```
