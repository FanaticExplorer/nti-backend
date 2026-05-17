"""Tests for /milestones endpoints."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_create_milestone(client: AsyncClient, nti_admin, application):
    r = await client.post(
        "/milestones",
        json={
            "application_id": str(application.id),
            "title": "MVP Delivery",
            "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 201
    assert r.json()["title"] == "MVP Delivery"


@pytest.mark.asyncio
async def test_list_milestones(client: AsyncClient, nti_admin, application):
    await client.post(
        "/milestones",
        json={
            "application_id": str(application.id),
            "title": "MVP Delivery",
            "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
        headers=auth_headers(nti_admin),
    )
    r = await client.get(
        f"/milestones/{application.id}", headers=auth_headers(nti_admin)
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_update_milestone_status(client: AsyncClient, nti_admin, application):
    r = await client.post(
        "/milestones",
        json={
            "application_id": str(application.id),
            "title": "MVP Delivery",
            "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
        headers=auth_headers(nti_admin),
    )
    m_id = r.json()["id"]

    r = await client.patch(
        f"/milestones/{m_id}/status",
        json={"status": "completed"},
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
