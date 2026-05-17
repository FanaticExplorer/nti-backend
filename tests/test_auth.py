"""Tests for /auth endpoints: register, login, refresh, verify-email, forgot/reset password, /me."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_creates_user(client: AsyncClient):
    r = await client.post(
        "/auth/register",
        json={
            "email": "newuser@test.com",
            "password": "securepass123",
            "full_name": "New User",
            "role": "student",
            "gdpr_consent": True,
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == "newuser@test.com"
    assert data["role"] == "student"
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient, student):
    r = await client.post(
        "/auth/register",
        json={
            "email": student.email,
            "password": "securepass123",
            "full_name": "Duplicate",
            "role": "student",
            "gdpr_consent": True,
        },
    )
    assert r.status_code == 409
    assert "already registered" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_gdpr_consent_defaults_true(client: AsyncClient):
    """When gdpr_consent is omitted, it defaults to True."""
    r = await client.post(
        "/auth/register",
        json={
            "email": "defaultgdpr@test.com",
            "password": "securepass123",
            "full_name": "Default GDPR",
            "role": "student",
        },
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_login_returns_tokens(client: AsyncClient, student):
    r = await client.post(
        "/auth/login",
        json={
            "email": student.email,
            "password": "testpass123",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_bad_password_returns_401(client: AsyncClient, student):
    r = await client.post(
        "/auth/login",
        json={
            "email": student.email,
            "password": "wrongpassword",
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user_returns_403(client: AsyncClient, user_factory):
    u = await user_factory(role="student", is_active=False)
    r = await client.post(
        "/auth/login",
        json={
            "email": u.email,
            "password": "testpass123",
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_refresh_returns_new_tokens(client: AsyncClient, student):
    from app.utils.security import create_refresh_token

    refresh = create_refresh_token({"sub": str(student.id), "role": student.role})
    r = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_bad_token_returns_401(client: AsyncClient):
    r = await client.post("/auth/refresh", json={"refresh_token": "garbage"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_verify_email_sets_flag(client: AsyncClient, user_factory):
    from app.utils.security import create_access_token

    u = await user_factory(role="student", is_email_verified=False)
    token = create_access_token({"sub": str(u.id), "purpose": "email_verify"})
    r = await client.post(f"/auth/verify-email?token={token}")
    assert r.status_code == 200
    assert r.json()["detail"] == "Email verified successfully"


@pytest.mark.asyncio
async def test_verify_email_bad_token_returns_400(client: AsyncClient):
    r = await client.post("/auth/verify-email?token=garbage")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_forgot_password_always_returns_200(client: AsyncClient, student):
    """Anti-enumeration: always return 200 whether email exists or not."""
    r = await client.post("/auth/forgot-password", json={"email": student.email})
    assert r.status_code == 200
    r = await client.post(
        "/auth/forgot-password", json={"email": "nonexistent@test.com"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_works(client: AsyncClient, student):
    from app.utils.security import create_access_token

    token = create_access_token({"sub": str(student.id), "purpose": "password_reset"})
    r = await client.post(
        "/auth/reset-password",
        json={
            "token": token,
            "new_password": "newsecurepass456",
        },
    )
    assert r.status_code == 200

    # Old password should no longer work
    r = await client.post(
        "/auth/login",
        json={
            "email": student.email,
            "password": "testpass123",
        },
    )
    assert r.status_code == 401

    # New password should work
    r = await client.post(
        "/auth/login",
        json={
            "email": student.email,
            "password": "newsecurepass456",
        },
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_get_me_returns_current_user(client: AsyncClient, student):
    from tests.conftest import auth_headers

    r = await client.get("/auth/me", headers=auth_headers(student))
    assert r.status_code == 200
    assert r.json()["email"] == student.email
    assert r.json()["role"] == student.role


@pytest.mark.asyncio
async def test_get_me_without_token_returns_401(client: AsyncClient):
    r = await client.get("/auth/me")
    assert r.status_code == 401
