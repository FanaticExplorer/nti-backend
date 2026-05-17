"""Tests for /documents endpoints."""

import io

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_upload_document(client: AsyncClient, student, application):
    r = await client.post(
        "/documents?application_id=" + str(application.id),
        files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        headers=auth_headers(student),
    )
    assert r.status_code == 201
    assert r.json()["filename"] == "test.pdf"


@pytest.mark.asyncio
async def test_upload_wrong_mime_type(client: AsyncClient, student, application):
    r = await client.post(
        "/documents?application_id=" + str(application.id),
        files={"file": ("test.exe", io.BytesIO(b"bad"), "application/x-msdownload")},
        headers=auth_headers(student),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_download_document(client: AsyncClient, student, application):
    # Upload first
    r = await client.post(
        "/documents?application_id=" + str(application.id),
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 content"), "application/pdf")},
        headers=auth_headers(student),
    )
    doc_id = r.json()["id"]

    r = await client.get(f"/documents/{doc_id}", headers=auth_headers(student))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient, student, application):
    r = await client.post(
        "/documents?application_id=" + str(application.id),
        files={"file": ("tmp.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        headers=auth_headers(student),
    )
    doc_id = r.json()["id"]

    r = await client.delete(f"/documents/{doc_id}", headers=auth_headers(student))
    assert r.status_code == 204
