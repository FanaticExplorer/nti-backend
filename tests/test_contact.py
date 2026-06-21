import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_message import ContactMessage
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_submit_contact_message(client: AsyncClient):
    response = await client.post(
        "/content/contact",
        json={"name": "John", "email": "john@example.com", "message": "Hello there"},
    )
    assert response.status_code == 200
    assert response.json() == {"detail": "Message sent"}


@pytest.mark.asyncio
async def test_submit_contact_message_missing_fields(client: AsyncClient):
    response = await client.post("/content/contact", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_contact_message_invalid_email(client: AsyncClient):
    response = await client.post(
        "/content/contact",
        json={"name": "John", "email": "not-an-email", "message": "Hi"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_contact_message_empty_name(client: AsyncClient):
    response = await client.post(
        "/content/contact",
        json={"name": "", "email": "john@example.com", "message": "Hi"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_contact_message_empty_message(client: AsyncClient):
    response = await client.post(
        "/content/contact",
        json={"name": "John", "email": "john@example.com", "message": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_contact_message_persisted(
    client: AsyncClient, db: AsyncSession
):
    response = await client.post(
        "/content/contact",
        json={"name": "Jane", "email": "jane@example.com", "message": "Need help"},
    )
    assert response.status_code == 200

    result = await db.execute(
        select(ContactMessage).where(ContactMessage.email == "jane@example.com")
    )
    msg = result.scalar_one_or_none()
    assert msg is not None
    assert msg.name == "Jane"
    assert msg.message == "Need help"
    assert msg.is_read is False


@pytest.mark.asyncio
async def test_list_contact_messages_as_admin(
    client: AsyncClient, db: AsyncSession, nti_admin
):
    msg = ContactMessage(
        id=uuid.uuid4(), name="Test", email="test@test.com", message="Msg"
    )
    db.add(msg)
    await db.commit()

    response = await client.get(
        "/content/contact-messages", headers=auth_headers(nti_admin)
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(m["email"] == "test@test.com" for m in data["items"])


@pytest.mark.asyncio
async def test_list_contact_messages_filter_is_read(
    client: AsyncClient, db: AsyncSession, nti_admin
):
    msg_read = ContactMessage(
        id=uuid.uuid4(), name="Read", email="read@test.com", message="X", is_read=True
    )
    msg_unread = ContactMessage(
        id=uuid.uuid4(), name="Unread", email="unread@test.com", message="Y", is_read=False
    )
    db.add_all([msg_read, msg_unread])
    await db.commit()

    response = await client.get(
        "/content/contact-messages",
        params={"is_read": "true"},
        headers=auth_headers(nti_admin),
    )
    assert response.status_code == 200
    data = response.json()
    assert all(m["is_read"] for m in data["items"])

    response = await client.get(
        "/content/contact-messages",
        params={"is_read": "false"},
        headers=auth_headers(nti_admin),
    )
    assert response.status_code == 200
    data = response.json()
    assert all(not m["is_read"] for m in data["items"])


@pytest.mark.asyncio
async def test_list_contact_messages_requires_admin(
    client: AsyncClient, student
):
    response = await client.get(
        "/content/contact-messages", headers=auth_headers(student)
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_contact_messages_requires_auth(client: AsyncClient):
    response = await client.get("/content/contact-messages")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_toggle_contact_message_read(
    client: AsyncClient, db: AsyncSession, nti_admin
):
    msg = ContactMessage(
        id=uuid.uuid4(), name="Toggle", email="toggle@test.com", message="X"
    )
    db.add(msg)
    await db.commit()

    response = await client.patch(
        f"/content/contact-messages/{msg.id}/read",
        headers=auth_headers(nti_admin),
    )
    assert response.status_code == 200
    assert response.json()["is_read"] is True

    response = await client.patch(
        f"/content/contact-messages/{msg.id}/read",
        headers=auth_headers(nti_admin),
    )
    assert response.status_code == 200
    assert response.json()["is_read"] is False


@pytest.mark.asyncio
async def test_toggle_contact_message_read_not_found(
    client: AsyncClient, nti_admin
):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.patch(
        f"/content/contact-messages/{fake_id}/read",
        headers=auth_headers(nti_admin),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_toggle_contact_message_read_requires_admin(
    client: AsyncClient, db: AsyncSession, student
):
    msg = ContactMessage(
        id=uuid.uuid4(), name="X", email="x@test.com", message="Y"
    )
    db.add(msg)
    await db.commit()

    response = await client.patch(
        f"/content/contact-messages/{msg.id}/read",
        headers=auth_headers(student),
    )
    assert response.status_code == 403
