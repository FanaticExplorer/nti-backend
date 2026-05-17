"""Tests for /applications endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_create_application(client: AsyncClient, student, call):
    r = await client.post(
        "/applications",
        json={
            "call_id": str(call.id),
            "form_data": {"project": "My Project"},
        },
        headers=auth_headers(student),
    )
    assert r.status_code == 201
    assert r.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_get_my_applications(client: AsyncClient, student, application):
    r = await client.get("/applications/my", headers=auth_headers(student))
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_list_applications_as_admin(client: AsyncClient, nti_admin, application):
    r = await client.get("/applications", headers=auth_headers(nti_admin))
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_get_application_as_owner(client: AsyncClient, student, application):
    r = await client.get(
        f"/applications/{application.id}", headers=auth_headers(student)
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_get_application_as_non_owner_returns_403(
    client: AsyncClient, user_factory, application
):
    other = await user_factory(role="student")
    r = await client.get(f"/applications/{application.id}", headers=auth_headers(other))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_draft_application(client: AsyncClient, student, application):
    r = await client.put(
        f"/applications/{application.id}",
        json={"form_data": {"project": "Updated Project"}},
        headers=auth_headers(student),
    )
    assert r.status_code == 200
    assert r.json()["form_data"]["project"] == "Updated Project"


@pytest.mark.asyncio
async def test_submit_program_a_without_team_fails(client: AsyncClient, student, call):
    """Program A submission without team_id and documents should fail."""
    r = await client.post(
        "/applications",
        json={
            "call_id": str(call.id),
            "form_data": {"project": "Simple Project"},
        },
        headers=auth_headers(student),
    )
    app_id = r.json()["id"]

    r = await client.post(
        f"/applications/{app_id}/submit", headers=auth_headers(student)
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_submit_requires_team_for_program_a(
    client: AsyncClient, student, call, program
):
    """Program A submission without team_id should fail."""
    r = await client.post(
        "/applications",
        json={
            "call_id": str(call.id),
        },
        headers=auth_headers(student),
    )
    app_id = r.json()["id"]
    r = await client.post(
        f"/applications/{app_id}/submit", headers=auth_headers(student)
    )
    assert r.status_code == 422
    assert "team" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_application_status_transition(
    client: AsyncClient, nti_admin, application
):
    """Admin transitions an application through valid statuses."""
    # draft → submitted
    application.is_draft = False
    application.status = "submitted"

    r = await client.patch(
        f"/applications/{application.id}/status",
        json={"status": "formally_verified"},
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "formally_verified"


@pytest.mark.asyncio
async def test_invalid_status_transition_returns_422(
    client: AsyncClient, nti_admin, application
):
    """Cannot jump from draft to approved."""
    r = await client.patch(
        f"/applications/{application.id}/status",
        json={"status": "approved"},
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_get_application_history(client: AsyncClient, student, application):
    r = await client.get(
        f"/applications/{application.id}/history", headers=auth_headers(student)
    )
    assert r.status_code == 200
    assert "items" in r.json()
