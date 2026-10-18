"""
Shared fixtures for API tests.

All tests mock the database and override verify_api_key so no real DB is needed.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.auth import verify_api_key
from app.clients.db import get_db
from app.main import app

ORG_ID = "aaaaaaaa-0000-0000-0000-000000000001"
AGENT_ID = "aaaaaaaa-0000-0000-0000-000000000002"
VERSION_ID = "aaaaaaaa-0000-0000-0000-000000000003"
RUN_ID = "aaaaaaaa-0000-0000-0000-000000000004"
SPAN_ID = "aaaaaaaa-0000-0000-0000-000000000005"
EVENT_ID = "aaaaaaaa-0000-0000-0000-000000000006"


def make_exec(*, mapping=None, first=True, scalar=0, all=None):
    """
    Build a mock SQLAlchemy execute() return value.

    mapping  - value returned by .mappings().first()
    first    - truthy/falsy for .first() (used by assert_*_org helpers)
    scalar   - value returned by .scalar() (used by COUNT queries)
    all      - list returned by .mappings().all()
    """
    result = MagicMock()
    result.mappings.return_value.first.return_value = mapping
    result.mappings.return_value.all.return_value = all or []
    result.first.return_value = MagicMock() if first else None
    result.scalar.return_value = scalar
    return result


@pytest.fixture
def db():
    mock = MagicMock()
    mock.commit.return_value = None
    return mock


@pytest.fixture
def client(db):
    app.dependency_overrides[verify_api_key] = lambda: ORG_ID
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client():
    yield TestClient(app)
