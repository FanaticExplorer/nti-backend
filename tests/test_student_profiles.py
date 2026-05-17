"""Tests for /profiles endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_create_profile(client: AsyncClient, student):
    r = await client.post(
        "/profiles",
        json={
            "university": "CU",
            "faculty": "FMFI",
            "study_program": "CS",
            "year_of_study": 2,
        },
        headers=auth_headers(student),
    )
    assert r.status_code == 201
    assert r.json()["university"] == "CU"


@pytest.mark.asyncio
async def test_create_profile_already_exists_returns_409(client: AsyncClient, student):
    await client.post(
        "/profiles",
        json={
            "university": "CU",
            "faculty": "FMFI",
            "study_program": "CS",
            "year_of_study": 2,
        },
        headers=auth_headers(student),
    )
    r = await client.post(
        "/profiles",
        json={
            "university": "CU",
            "faculty": "FMFI",
            "study_program": "CS",
            "year_of_study": 2,
        },
        headers=auth_headers(student),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_get_my_profile(client: AsyncClient, student):
    await client.post(
        "/profiles",
        json={
            "university": "CU",
            "faculty": "FMFI",
            "study_program": "CS",
            "year_of_study": 2,
        },
        headers=auth_headers(student),
    )
    r = await client.get("/profiles/me", headers=auth_headers(student))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_get_my_profile_not_found_returns_404(client: AsyncClient, student):
    r = await client.get("/profiles/me", headers=auth_headers(student))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_my_profile(client: AsyncClient, student):
    await client.post(
        "/profiles",
        json={
            "university": "CU",
            "faculty": "FMFI",
            "study_program": "CS",
            "year_of_study": 2,
        },
        headers=auth_headers(student),
    )
    r = await client.put(
        "/profiles/me", json={"university": "UK"}, headers=auth_headers(student)
    )
    assert r.status_code == 200
    assert r.json()["university"] == "UK"


@pytest.mark.asyncio
async def test_get_profile_by_user_id_as_admin(client: AsyncClient, nti_admin, student):
    await client.post(
        "/profiles",
        json={
            "university": "CU",
            "faculty": "FMFI",
            "study_program": "CS",
            "year_of_study": 2,
        },
        headers=auth_headers(student),
    )
    r = await client.get(f"/profiles/{student.id}", headers=auth_headers(nti_admin))
    assert r.status_code == 200
