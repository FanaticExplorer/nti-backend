import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_list_members(client: AsyncClient, organization, firm_user):
    r = await client.get(
        f"/organizations/{organization.id}/members",
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["role_in_org"] == "owner"


@pytest.mark.asyncio
async def test_add_member_as_owner(client: AsyncClient, organization, firm_user, student):
    r = await client.post(
        f"/organizations/{organization.id}/members",
        json={"user_id": str(student.id), "role_in_org": "member"},
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 200

    r = await client.get(
        f"/organizations/{organization.id}/members",
        headers=auth_headers(firm_user),
    )
    assert len(r.json()["items"]) == 2


@pytest.mark.asyncio
async def test_add_member_duplicate(client: AsyncClient, organization, firm_user, student):
    await client.post(
        f"/organizations/{organization.id}/members",
        json={"user_id": str(student.id), "role_in_org": "member"},
        headers=auth_headers(firm_user),
    )
    r = await client.post(
        f"/organizations/{organization.id}/members",
        json={"user_id": str(student.id), "role_in_org": "member"},
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_add_member_invalid_role(client: AsyncClient, organization, firm_user, student):
    r = await client.post(
        f"/organizations/{organization.id}/members",
        json={"user_id": str(student.id), "role_in_org": "superhero"},
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_member_role(client: AsyncClient, organization, firm_user, student):
    await client.post(
        f"/organizations/{organization.id}/members",
        json={"user_id": str(student.id), "role_in_org": "member"},
        headers=auth_headers(firm_user),
    )
    r = await client.patch(
        f"/organizations/{organization.id}/members/{student.id}",
        json={"role_in_org": "admin"},
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 200

    r = await client.get(
        f"/organizations/{organization.id}/members",
        headers=auth_headers(firm_user),
    )
    roles = {m["user_id"]: m["role_in_org"] for m in r.json()["items"]}
    assert roles[str(student.id)] == "admin"


@pytest.mark.asyncio
async def test_remove_member(client: AsyncClient, organization, firm_user, student):
    await client.post(
        f"/organizations/{organization.id}/members",
        json={"user_id": str(student.id), "role_in_org": "member"},
        headers=auth_headers(firm_user),
    )
    r = await client.delete(
        f"/organizations/{organization.id}/members/{student.id}",
        headers=auth_headers(firm_user),
    )
    assert r.status_code == 200

    r = await client.get(
        f"/organizations/{organization.id}/members",
        headers=auth_headers(firm_user),
    )
    assert len(r.json()["items"]) == 1


@pytest.mark.asyncio
async def test_add_member_as_admin(client: AsyncClient, organization, nti_admin, student):
    r = await client.post(
        f"/organizations/{organization.id}/members",
        json={"user_id": str(student.id), "role_in_org": "product_owner"},
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_list_members_denied_for_non_member(
    client: AsyncClient, organization, student
):
    r = await client.get(
        f"/organizations/{organization.id}/members",
        headers=auth_headers(student),
    )
    assert r.status_code == 403
