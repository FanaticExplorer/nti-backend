"""Tests for /admin endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_stats_requires_admin(client: AsyncClient, student):
    r = await client.get("/admin/stats", headers=auth_headers(student))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_stats_as_admin(client: AsyncClient, nti_admin):
    r = await client.get("/admin/stats", headers=auth_headers(nti_admin))
    assert r.status_code == 200
    data = r.json()
    assert "total_users" in data
    assert "total_applications" in data
    assert "total_programs" in data


@pytest.mark.asyncio
async def test_audit_log_requires_super_admin(client: AsyncClient, nti_admin):
    r = await client.get("/admin/audit-log", headers=auth_headers(nti_admin))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_audit_log_as_super_admin(client: AsyncClient, super_admin):
    r = await client.get("/admin/audit-log", headers=auth_headers(super_admin))
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_export_applications_csv(client: AsyncClient, nti_admin):
    r = await client.get("/admin/export/applications", headers=auth_headers(nti_admin))
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
