"""Tests for /organizations endpoints."""

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_create_org_as_firm(client: AsyncClient, firm_user):
    r = await client.post(
        "/organizations",
        json={
            "name": "My Org",
            "contact_email": "org@test.com",
        },
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 201
    assert r.json()["name"] == "My Org"


@pytest.mark.asyncio
async def test_create_org_as_student_returns_403(client: AsyncClient, student):
    r = await client.post(
        "/organizations",
        json={"name": "Nope", "contact_email": "org@test.com"},
        headers=auth_headers(student),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_orgs_as_admin(client: AsyncClient, nti_admin, organization):
    r = await client.get("/organizations", headers=auth_headers(nti_admin))
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_get_org_as_firm_member(client: AsyncClient, firm_user, organization):
    r = await client.get(
        f"/organizations/{organization.id}", headers=auth_headers(firm_user)
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_approve_org(client: AsyncClient, nti_admin, organization):
    r = await client.patch(
        f"/organizations/{organization.id}/approve", headers=auth_headers(nti_admin)
    )
    assert r.status_code == 200
    assert r.json()["detail"] == "Organization approved"


@pytest.mark.asyncio
async def test_add_member_to_org(client: AsyncClient, firm_user, organization, student):
    r = await client.post(
        f"/organizations/{organization.id}/members",
        json={
            "user_id": str(student.id),
            "role_in_org": "member",
        },
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 200
    assert r.json()["detail"] == "Member added"
