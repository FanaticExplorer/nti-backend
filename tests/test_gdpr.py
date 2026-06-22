import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_export_my_data(client: AsyncClient, student):
    r = await client.get("/users/me/export", headers=auth_headers(student))
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["email"] == student.email
    assert data["user"]["full_name"] == student.full_name
    assert "applications" in data
    assert "organizations" in data
    assert "notifications" in data
    assert "exported_at" in data


@pytest.mark.asyncio
async def test_export_my_data_requires_auth(client: AsyncClient):
    r = await client.get("/users/me/export")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_anonymize_my_account(
    client: AsyncClient, db: AsyncSession, student
):
    old_email = student.email
    r = await client.delete("/users/me", headers=auth_headers(student))
    assert r.status_code == 200
    assert r.json() == {"detail": "Account anonymized"}

    await db.refresh(student)
    assert student.email != old_email
    assert "anonymized_" in student.email
    assert "@deleted.nti.sk" in student.email
    assert student.full_name == "Deleted User"
    assert student.hashed_password == ""
    assert student.is_active is False


@pytest.mark.asyncio
async def test_anonymize_my_account_requires_auth(client: AsyncClient):
    r = await client.delete("/users/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_anonymized_user_cannot_access_api(
    client: AsyncClient, db: AsyncSession, student
):
    token_before = auth_headers(student)
    await client.delete("/users/me", headers=token_before)

    r = await client.get("/users/me/export", headers=token_before)
    assert r.status_code == 403
