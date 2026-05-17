"""Tests for the health-check endpoint."""

import pytest


async def test_health_check_returns_ok(client):
    """GET /health should return 200 with ``{"status": "ok"}``."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
