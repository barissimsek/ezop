"""Tests for API key authentication."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.clients.db import get_db
from app.main import app


def _db_returns_none():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.first.return_value = None
    db.commit.return_value = None
    return db


client = TestClient(app, raise_server_exceptions=False)


def test_missing_auth_returns_401():
    app.dependency_overrides[get_db] = _db_returns_none
    try:
        resp = client.get("/agents/some-id/runs")
        assert resp.status_code == 401
        assert resp.json()["success"] is False
    finally:
        app.dependency_overrides.clear()


def test_invalid_api_key_returns_403():
    app.dependency_overrides[get_db] = _db_returns_none
    try:
        resp = client.get(
            "/agents/some-id/runs",
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert resp.status_code == 403
        assert resp.json()["success"] is False
    finally:
        app.dependency_overrides.clear()


def test_error_response_envelope():
    app.dependency_overrides[get_db] = _db_returns_none
    try:
        resp = client.get("/agents/some-id/runs")
        body = resp.json()
        assert "success" in body
        assert "data" in body
        assert "error" in body
    finally:
        app.dependency_overrides.clear()
