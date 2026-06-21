import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.utils.notifications import create_notification
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_list_notifications_empty(client: AsyncClient, student):
    r = await client.get("/notifications", headers=auth_headers(student))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_notifications_with_data(
    client: AsyncClient, db: AsyncSession, student
):
    await create_notification(db, student.id, "Title 1", "Body 1", "test")
    await create_notification(db, student.id, "Title 2", "Body 2", "test")

    r = await client.get("/notifications", headers=auth_headers(student))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    titles = {item["title"] for item in data["items"]}
    assert titles == {"Title 1", "Title 2"}


@pytest.mark.asyncio
async def test_list_notifications_filter_is_read(
    client: AsyncClient, db: AsyncSession, student
):
    n1 = Notification(
        id=uuid.uuid4(), user_id=student.id, title="Read", body="X",
        action_type="test", is_read=True
    )
    n2 = Notification(
        id=uuid.uuid4(), user_id=student.id, title="Unread", body="Y",
        action_type="test", is_read=False
    )
    db.add_all([n1, n2])
    await db.commit()

    r = await client.get(
        "/notifications", params={"is_read": "false"}, headers=auth_headers(student)
    )
    assert r.status_code == 200
    data = r.json()
    assert all(not item["is_read"] for item in data["items"])

    r = await client.get(
        "/notifications", params={"is_read": "true"}, headers=auth_headers(student)
    )
    assert r.status_code == 200
    data = r.json()
    assert all(item["is_read"] for item in data["items"])


@pytest.mark.asyncio
async def test_notifications_requires_auth(client: AsyncClient):
    r = await client.get("/notifications")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_unread_count(
    client: AsyncClient, db: AsyncSession, student
):
    await create_notification(db, student.id, "T", "B", "test")
    await create_notification(db, student.id, "T", "B", "test")

    r = await client.get("/notifications/unread-count", headers=auth_headers(student))
    assert r.status_code == 200
    assert r.json()["count"] == 2


@pytest.mark.asyncio
async def test_toggle_notification_read(
    client: AsyncClient, db: AsyncSession, student
):
    await create_notification(db, student.id, "T", "B", "test")
    result = await db.execute(
        select(Notification).where(Notification.user_id == student.id)
    )
    notif = result.scalar_one()

    r = await client.patch(
        f"/notifications/{notif.id}/read", headers=auth_headers(student)
    )
    assert r.status_code == 200
    assert r.json()["is_read"] is True

    r = await client.patch(
        f"/notifications/{notif.id}/read", headers=auth_headers(student)
    )
    assert r.status_code == 200
    assert r.json()["is_read"] is False


@pytest.mark.asyncio
async def test_toggle_notification_read_wrong_user(
    client: AsyncClient, db: AsyncSession, student, nti_admin
):
    await create_notification(db, student.id, "T", "B", "test")
    result = await db.execute(
        select(Notification).where(Notification.user_id == student.id)
    )
    notif = result.scalar_one()

    r = await client.patch(
        f"/notifications/{notif.id}/read", headers=auth_headers(nti_admin)
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_toggle_notification_read_not_found(client: AsyncClient, student):
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = await client.patch(
        f"/notifications/{fake_id}/read", headers=auth_headers(student)
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_read(
    client: AsyncClient, db: AsyncSession, student
):
    await create_notification(db, student.id, "T1", "B1", "test")
    await create_notification(db, student.id, "T2", "B2", "test")

    r = await client.patch("/notifications/read-all", headers=auth_headers(student))
    assert r.status_code == 200
    assert r.json()["detail"] == "All notifications marked as read"

    r = await client.get("/notifications/unread-count", headers=auth_headers(student))
    assert r.json()["count"] == 0
