import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_comment import ApplicationComment
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_list_comments_empty(client: AsyncClient, application, student):
    r = await client.get(
        f"/applications/{application.id}/comments", headers=auth_headers(student)
    )
    assert r.status_code == 200
    assert r.json()["items"] == []


@pytest.mark.asyncio
async def test_add_comment_as_evaluator(
    client: AsyncClient, db: AsyncSession, application, evaluator, student
):
    r = await client.post(
        f"/applications/{application.id}/comments",
        json={"body": "Looks good", "is_internal": False},
        headers=auth_headers(evaluator),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["body"] == "Looks good"
    assert data["user_id"] == str(evaluator.id)
    assert data["user_name"] == evaluator.full_name
    assert data["is_internal"] is False


@pytest.mark.asyncio
async def test_add_comment_requires_role(
    client: AsyncClient, application, student
):
    r = await client.post(
        f"/applications/{application.id}/comments",
        json={"body": "I want to comment"},
        headers=auth_headers(student),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_comments_as_owner(
    client: AsyncClient, db: AsyncSession, application, evaluator, student
):
    comment = ApplicationComment(
        id=uuid.uuid4(), application_id=application.id,
        user_id=evaluator.id, body="Public note", is_internal=False,
    )
    db.add(comment)
    await db.commit()

    r = await client.get(
        f"/applications/{application.id}/comments", headers=auth_headers(student)
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["body"] == "Public note"


@pytest.mark.asyncio
async def test_internal_comments_hidden_from_student(
    client: AsyncClient, db: AsyncSession, application, evaluator, student
):
    pub = ApplicationComment(
        id=uuid.uuid4(), application_id=application.id,
        user_id=evaluator.id, body="Public", is_internal=False,
    )
    priv = ApplicationComment(
        id=uuid.uuid4(), application_id=application.id,
        user_id=evaluator.id, body="Internal secret", is_internal=True,
    )
    db.add_all([pub, priv])
    await db.commit()

    r = await client.get(
        f"/applications/{application.id}/comments", headers=auth_headers(student)
    )
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["body"] == "Public"


@pytest.mark.asyncio
async def test_internal_comments_visible_to_evaluator(
    client: AsyncClient, db: AsyncSession, application, evaluator
):
    pub = ApplicationComment(
        id=uuid.uuid4(), application_id=application.id,
        user_id=evaluator.id, body="Public", is_internal=False,
    )
    priv = ApplicationComment(
        id=uuid.uuid4(), application_id=application.id,
        user_id=evaluator.id, body="Internal", is_internal=True,
    )
    db.add_all([pub, priv])
    await db.commit()

    r = await client.get(
        f"/applications/{application.id}/comments", headers=auth_headers(evaluator)
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2


@pytest.mark.asyncio
async def test_list_comments_access_denied(
    client: AsyncClient, application, firm_user
):
    r = await client.get(
        f"/applications/{application.id}/comments", headers=auth_headers(firm_user)
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_add_comment_creates_notification(
    client: AsyncClient, application, evaluator
):
    r = await client.post(
        f"/applications/{application.id}/comments",
        json={"body": "Needs review"},
        headers=auth_headers(evaluator),
    )
    assert r.status_code == 201

    r_notif = await client.get(
        "/notifications", headers=auth_headers(application.applicant)
    )
    notifs = r_notif.json()["items"]
    assert any(n["action_type"] == "comment_added" for n in notifs)
