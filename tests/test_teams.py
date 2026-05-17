"""Tests for /teams endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_create_team_as_student(client: AsyncClient, student):
    r = await client.post(
        "/teams",
        json={"name": "My Team", "program_type": "A"},
        headers=auth_headers(student),
    )
    assert r.status_code == 201
    assert r.json()["name"] == "My Team"


@pytest.mark.asyncio
async def test_get_my_teams(client: AsyncClient, team_leader, team):
    r = await client.get("/teams/my", headers=auth_headers(team_leader))
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_get_team_with_members(client: AsyncClient, team_leader, team):
    r = await client.get(f"/teams/{team.id}", headers=auth_headers(team_leader))
    assert r.status_code == 200
    data = r.json()
    assert "members" in data
    assert len(data["members"]) >= 2


@pytest.mark.asyncio
async def test_join_team(client: AsyncClient, user_factory, team):
    new_student = await user_factory(role="student")
    r = await client.post(f"/teams/{team.id}/join", headers=auth_headers(new_student))
    assert r.status_code == 200
    assert r.json()["detail"] == "Joined team successfully"


@pytest.mark.asyncio
async def test_join_team_already_member_returns_409(client: AsyncClient, student, team):
    r = await client.post(f"/teams/{team.id}/join", headers=auth_headers(student))
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_remove_member(client: AsyncClient, team_leader, team, user_factory):
    extra = await user_factory(role="student")
    await client.post(f"/teams/{team.id}/join", headers=auth_headers(extra))
    r = await client.delete(
        f"/teams/{team.id}/members/{extra.id}", headers=auth_headers(team_leader)
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_remove_self_as_leader_returns_400(
    client: AsyncClient, team_leader, team
):
    r = await client.delete(
        f"/teams/{team.id}/members/{team_leader.id}", headers=auth_headers(team_leader)
    )
    assert r.status_code == 400
