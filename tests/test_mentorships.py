"""Tests for /mentorships endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_assign_mentor(client: AsyncClient, nti_admin, mentor, application):
    r = await client.post(
        "/mentorships",
        json={
            "application_id": str(application.id),
            "mentor_id": str(mentor.id),
        },
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_get_my_mentorships(client: AsyncClient, nti_admin, mentor, application):
    await client.post(
        "/mentorships",
        json={
            "application_id": str(application.id),
            "mentor_id": str(mentor.id),
        },
        headers=auth_headers(nti_admin),
    )
    r = await client.get("/mentorships/my", headers=auth_headers(mentor))
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_add_mentorship_log(client: AsyncClient, nti_admin, mentor, application):
    r = await client.post(
        "/mentorships",
        json={
            "application_id": str(application.id),
            "mentor_id": str(mentor.id),
        },
        headers=auth_headers(nti_admin),
    )
    m_id = r.json()["id"]

    r = await client.post(
        f"/mentorships/{m_id}/logs",
        json={"content": "First session notes"},
        headers=auth_headers(mentor),
    )
    assert r.status_code == 201
    assert r.json()["content"] == "First session notes"


@pytest.mark.asyncio
async def test_get_mentorship_logs(client: AsyncClient, nti_admin, mentor, application):
    r = await client.post(
        "/mentorships",
        json={
            "application_id": str(application.id),
            "mentor_id": str(mentor.id),
        },
        headers=auth_headers(nti_admin),
    )
    m_id = r.json()["id"]

    await client.post(
        f"/mentorships/{m_id}/logs",
        json={"content": "Log entry"},
        headers=auth_headers(mentor),
    )

    r = await client.get(f"/mentorships/{m_id}/logs", headers=auth_headers(mentor))
    assert r.status_code == 200
    assert r.json()["total"] >= 1
