"""Tests for /users endpoints: list, get, change role, deactivate."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_list_users_requires_admin(client: AsyncClient, student):
    r = await client.get("/users", headers=auth_headers(student))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_users_as_admin(client: AsyncClient, nti_admin, student):
    r = await client.get("/users", headers=auth_headers(nti_admin))
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_users_filter_by_role(
    client: AsyncClient, nti_admin, student, mentor
):
    r = await client.get("/users?role=mentor", headers=auth_headers(nti_admin))
    assert r.status_code == 200
    for u in r.json()["items"]:
        assert u["role"] == "mentor"


@pytest.mark.asyncio
async def test_get_user_by_id(client: AsyncClient, nti_admin, student):
    r = await client.get(f"/users/{student.id}", headers=auth_headers(nti_admin))
    assert r.status_code == 200
    assert r.json()["email"] == student.email


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient, nti_admin):
    import uuid

    r = await client.get(f"/users/{uuid.uuid4()}", headers=auth_headers(nti_admin))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_change_role_requires_super_admin(
    client: AsyncClient, nti_admin, student
):
    r = await client.patch(
        f"/users/{student.id}/role",
        json={"role": "mentor"},
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_change_role_as_super_admin(client: AsyncClient, super_admin, student):
    r = await client.patch(
        f"/users/{student.id}/role",
        json={"role": "mentor"},
        headers=auth_headers(super_admin),
    )
    assert r.status_code == 200
    assert r.json()["role"] == "mentor"


@pytest.mark.asyncio
async def test_deactivate_user(client: AsyncClient, nti_admin, student):
    r = await client.patch(
        f"/users/{student.id}/deactivate",
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False


@pytest.mark.asyncio
async def test_deactivate_user_not_found(client: AsyncClient, nti_admin):
    import uuid

    r = await client.patch(
        f"/users/{uuid.uuid4()}/deactivate",
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 404
