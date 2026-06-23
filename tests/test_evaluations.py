"""Tests for /evaluations endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_create_evaluation(client: AsyncClient, evaluator, application):
    r = await client.post(
        "/evaluations",
        json={
            "application_id": str(application.id),
            "score": 8.5,
            "recommendation": "approve",
            "comment": "Looks good",
        },
        headers=auth_headers(evaluator),
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_get_evaluations(client: AsyncClient, evaluator, application):
    await client.post(
        "/evaluations",
        json={
            "application_id": str(application.id),
            "score": 8.5,
            "recommendation": "approve",
        },
        headers=auth_headers(evaluator),
    )
    r = await client.get(
        f"/evaluations/{application.id}", headers=auth_headers(evaluator)
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_update_evaluation(client: AsyncClient, evaluator, application):
    r = await client.post(
        "/evaluations",
        json={
            "application_id": str(application.id),
            "score": 7.0,
            "recommendation": "approve",
        },
        headers=auth_headers(evaluator),
    )
    eval_id = r.json()["id"]

    r = await client.put(
        f"/evaluations/{eval_id}",
        json={
            "score": 9.0,
            "comment": "Revised upward",
        },
        headers=auth_headers(evaluator),
    )
    assert r.status_code == 200
    assert r.json()["score"] == 9.0
