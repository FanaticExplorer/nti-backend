import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.faq import FAQ
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_list_faq_public(client: AsyncClient, db: AsyncSession):
    db.add(FAQ(
        id=uuid.uuid4(), question="Q1", answer="A1", sort_order=1, is_published=True
    ))
    db.add(FAQ(
        id=uuid.uuid4(), question="Q2", answer="A2", sort_order=0, is_published=False
    ))
    await db.commit()

    r = await client.get("/content/faq")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["question"] == "Q1"


@pytest.mark.asyncio
async def test_list_faq_filter_category(client: AsyncClient, db: AsyncSession):
    db.add(FAQ(
        id=uuid.uuid4(), question="Cat Q", answer="A", category="billing",
        is_published=True
    ))
    db.add(FAQ(
        id=uuid.uuid4(), question="Gen Q", answer="A", category="general",
        is_published=True
    ))
    await db.commit()

    r = await client.get("/content/faq", params={"category": "billing"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["category"] == "billing"


@pytest.mark.asyncio
async def test_create_faq_as_content_editor(client: AsyncClient, content_editor):
    r = await client.post(
        "/content/faq",
        json={"question": "How?", "answer": "Yes"},
        headers=auth_headers(content_editor),
    )
    assert r.status_code == 201
    assert r.json()["question"] == "How?"


@pytest.mark.asyncio
async def test_create_faq_requires_role(client: AsyncClient, student):
    r = await client.post(
        "/content/faq",
        json={"question": "How?", "answer": "Yes"},
        headers=auth_headers(student),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_faq(client: AsyncClient, db: AsyncSession, content_editor):
    faq = FAQ(id=uuid.uuid4(), question="Old", answer="Old", is_published=True)
    db.add(faq)
    await db.commit()

    r = await client.patch(
        f"/content/faq/{faq.id}",
        json={"question": "New"},
        headers=auth_headers(content_editor),
    )
    assert r.status_code == 200
    assert r.json()["question"] == "New"
    assert r.json()["answer"] == "Old"


@pytest.mark.asyncio
async def test_update_faq_not_found(client: AsyncClient, content_editor):
    r = await client.patch(
        "/content/faq/00000000-0000-0000-0000-000000000000",
        json={"question": "X"},
        headers=auth_headers(content_editor),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_faq(client: AsyncClient, db: AsyncSession, content_editor):
    faq = FAQ(id=uuid.uuid4(), question="Del", answer="Del", is_published=True)
    db.add(faq)
    await db.commit()

    r = await client.delete(
        f"/content/faq/{faq.id}", headers=auth_headers(content_editor)
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_delete_faq_not_found(client: AsyncClient, content_editor):
    r = await client.delete(
        "/content/faq/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(content_editor),
    )
    assert r.status_code == 404
