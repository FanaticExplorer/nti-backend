"""Tests for /programs endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_list_programs_public(client: AsyncClient, program):
    r = await client.get("/programs")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert data["items"][0]["title"] == "Test Program A"


@pytest.mark.asyncio
async def test_get_program(client: AsyncClient, program):
    r = await client.get(f"/programs/{program.id}")
    assert r.status_code == 200
    assert r.json()["type"] == "A"


@pytest.mark.asyncio
async def test_get_program_not_found(client: AsyncClient):
    import uuid

    r = await client.get(f"/programs/{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_program_requires_admin(client: AsyncClient, student):
    r = await client.post(
        "/programs",
        json={"title": "Unauthorized", "type": "A", "description": "nope"},
        headers=auth_headers(student),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_program_as_admin(client: AsyncClient, nti_admin):
    r = await client.post(
        "/programs",
        json={"title": "New Program", "type": "B", "description": "A new program"},
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 201
    assert r.json()["title"] == "New Program"


@pytest.mark.asyncio
async def test_update_program(client: AsyncClient, nti_admin, program):
    r = await client.put(
        f"/programs/{program.id}",
        json={"title": "Updated Title"},
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Updated Title"
