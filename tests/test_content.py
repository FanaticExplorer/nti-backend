"""Tests for /content endpoints — pages and news."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers

# ── Pages ──


@pytest.mark.asyncio
async def test_list_pages_public(client: AsyncClient):
    r = await client.get("/content/pages")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_create_page(client: AsyncClient, content_editor):
    r = await client.post(
        "/content/pages",
        json={
            "slug": "about-us",
            "title": "About Us",
            "body": "We are NTI",
            "is_published": True,
        },
        headers=auth_headers(content_editor),
    )
    assert r.status_code == 201
    assert r.json()["slug"] == "about-us"


@pytest.mark.asyncio
async def test_get_page_by_slug(client: AsyncClient, content_editor):
    await client.post(
        "/content/pages",
        json={
            "slug": "about-us",
            "title": "About Us",
            "body": "We are NTI",
            "is_published": True,
        },
        headers=auth_headers(content_editor),
    )
    r = await client.get("/content/pages/about-us")
    assert r.status_code == 200
    assert r.json()["title"] == "About Us"


@pytest.mark.asyncio
async def test_create_page_duplicate_slug_returns_409(
    client: AsyncClient, content_editor
):
    payload = {"slug": "unique", "title": "T", "body": "B", "is_published": True}
    await client.post(
        "/content/pages", json=payload, headers=auth_headers(content_editor)
    )
    r = await client.post(
        "/content/pages", json=payload, headers=auth_headers(content_editor)
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_get_unpublished_page_returns_404(
    client: AsyncClient, content_editor
):
    await client.post(
        "/content/pages",
        json={
            "slug": "draft-page",
            "title": "Draft",
            "body": "Not ready",
            "is_published": False,
        },
        headers=auth_headers(content_editor),
    )
    r = await client.get("/content/pages/draft-page")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_published_page_returns_seo_fields(
    client: AsyncClient, content_editor
):
    await client.post(
        "/content/pages",
        json={
            "slug": "seo-page",
            "title": "SEO Page",
            "body": "Content",
            "meta_title": "Custom Meta",
            "meta_description": "Custom description",
            "og_image_url": "https://example.com/img.png",
            "is_published": True,
        },
        headers=auth_headers(content_editor),
    )
    r = await client.get("/content/pages/seo-page")
    assert r.status_code == 200
    data = r.json()
    assert data["meta_title"] == "Custom Meta"
    assert data["meta_description"] == "Custom description"
    assert data["og_image_url"] == "https://example.com/img.png"


# ── News ──


@pytest.mark.asyncio
async def test_create_news_article(client: AsyncClient, content_editor):
    r = await client.post(
        "/content/news",
        json={
            "title": "Big Update",
            "slug": "big-update",
            "body": "We launched!",
            "is_published": True,
        },
        headers=auth_headers(content_editor),
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_list_news_public(client: AsyncClient, content_editor):
    await client.post(
        "/content/news",
        json={
            "title": "Big Update",
            "slug": "big-update",
            "body": "We launched!",
            "is_published": True,
        },
        headers=auth_headers(content_editor),
    )
    r = await client.get("/content/news")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_get_news_by_slug(client: AsyncClient, content_editor):
    await client.post(
        "/content/news",
        json={
            "title": "Big Update",
            "slug": "big-update",
            "body": "We launched!",
            "is_published": True,
        },
        headers=auth_headers(content_editor),
    )
    r = await client.get("/content/news/big-update")
    assert r.status_code == 200
