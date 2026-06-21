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


@pytest.mark.asyncio
async def test_upload_document_with_classification(
    client: AsyncClient, student, application
):
    r = await client.post(
        "/documents?application_id=" + str(application.id),
        files={"file": ("public.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"classification": "public"},
        headers=auth_headers(student),
    )
    assert r.status_code == 201
    assert r.json()["classification"] == "public"


@pytest.mark.asyncio
async def test_upload_document_with_type(
    client: AsyncClient, student, application
):
    r = await client.post(
        "/documents?application_id=" + str(application.id),
        files={"file": ("cv.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"document_type": "cv"},
        headers=auth_headers(student),
    )
    assert r.status_code == 201
    assert r.json()["document_type"] == "cv"


@pytest.mark.asyncio
async def test_confidential_document_blocked_for_student(
    client: AsyncClient, student, application
):
    r = await client.post(
        "/documents?application_id=" + str(application.id),
        files={"file": ("secret.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"classification": "confidential"},
        headers=auth_headers(student),
    )
    doc_id = r.json()["id"]

    r = await client.get(f"/documents/{doc_id}", headers=auth_headers(student))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_confidential_document_allowed_for_admin(
    client: AsyncClient, student, application, nti_admin
):
    r = await client.post(
        "/documents?application_id=" + str(application.id),
        files={"file": ("admin_secret.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"classification": "confidential"},
        headers=auth_headers(student),
    )
    doc_id = r.json()["id"]

    r = await client.get(f"/documents/{doc_id}", headers=auth_headers(nti_admin))
    assert r.status_code == 200
