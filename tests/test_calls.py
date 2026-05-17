"""Tests for /calls endpoints."""

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_list_calls_public(client: AsyncClient, call):
    r = await client.get("/calls")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_get_call(client: AsyncClient, call):
    r = await client.get(f"/calls/{call.id}")
    assert r.status_code == 200
    assert r.json()["title"] == "Test Call"


@pytest.mark.asyncio
async def test_get_call_not_found(client: AsyncClient):
    r = await client.get(f"/calls/{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_call_as_admin(client: AsyncClient, nti_admin, program):
    r = await client.post(
        "/calls",
        json={
            "program_id": str(program.id),
            "title": "New Call",
            "description": "A test call",
            "start_date": "2025-06-01T00:00:00Z",
            "end_date": "2025-07-01T00:00:00Z",
        },
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_create_call_as_firm_with_org(
    client: AsyncClient, firm_user, program, organization
):
    r = await client.post(
        "/calls",
        json={
            "program_id": str(program.id),
            "organization_id": str(organization.id),
            "title": "Firm Call",
            "description": "A firm call",
            "start_date": "2025-06-01T00:00:00Z",
            "end_date": "2025-07-01T00:00:00Z",
        },
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_create_call_as_firm_without_org_returns_400(
    client: AsyncClient, firm_user, program
):
    r = await client.post(
        "/calls",
        json={
            "program_id": str(program.id),
            "title": "Bad Firm Call",
            "description": "Missing org",
            "start_date": "2025-06-01T00:00:00Z",
            "end_date": "2025-07-01T00:00:00Z",
        },
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_create_call_as_student_returns_403(
    client: AsyncClient, student, program
):
    r = await client.post(
        "/calls",
        json={
            "program_id": str(program.id),
            "title": "Student Call",
            "description": "Should fail",
            "start_date": "2025-06-01T00:00:00Z",
            "end_date": "2025-07-01T00:00:00Z",
        },
        headers=auth_headers(student),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_call_own_as_firm(
    client: AsyncClient, firm_user, program, organization
):
    # Create a call as firm
    r = await client.post(
        "/calls",
        json={
            "program_id": str(program.id),
            "organization_id": str(organization.id),
            "title": "My Call",
            "description": "My firm call",
            "start_date": "2025-06-01T00:00:00Z",
            "end_date": "2025-07-01T00:00:00Z",
        },
        headers=auth_headers(firm_user),
    )
    call_id = r.json()["id"]

    r = await client.put(
        f"/calls/{call_id}",
        json={"title": "Updated Firm Call"},
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Updated Firm Call"


@pytest.mark.asyncio
async def test_change_call_status(client: AsyncClient, nti_admin, call):
    r = await client.patch(
        f"/calls/{call.id}/status",
        json={"status": "closed"},
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "closed"
