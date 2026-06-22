import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_sitemap(client: AsyncClient):
    r = await client.get("/content/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/xml"
    assert "<urlset" in r.text
    assert 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in r.text


@pytest.mark.asyncio
async def test_sitemap_has_no_auth(client: AsyncClient):
    r = await client.get("/content/sitemap.xml")
    assert r.status_code == 200
