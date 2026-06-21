import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_firm_dashboard_requires_firm_role(client: AsyncClient, student):
    r = await client.get("/tech-specs/firm/dashboard", headers=auth_headers(student))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_firm_dashboard_requires_auth(client: AsyncClient):
    r = await client.get("/tech-specs/firm/dashboard")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_firm_dashboard_no_org(client: AsyncClient, firm_user):
    r = await client.get(
        "/tech-specs/firm/dashboard", headers=auth_headers(firm_user)
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_firm_dashboard_with_org(client: AsyncClient, organization, firm_user):
    r = await client.get(
        "/tech-specs/firm/dashboard", headers=auth_headers(firm_user)
    )
    assert r.status_code == 200
    data = r.json()
    assert data["organization"]["name"] == organization.name
    assert "tech_specs_by_status" in data
    assert "total_tech_specs" in data
    assert "active_calls" in data
