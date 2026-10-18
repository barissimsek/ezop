"""Tests for the SQLAlchemy URL built from DATABASE_URL."""

import pytest
from sqlalchemy import create_engine

from app.clients.db import POSTGRES_DRIVER, sqlalchemy_url


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://ezop:secret@localhost:5432/ezop",
        "postgres://ezop:secret@localhost:5432/ezop",
    ],
)
def test_bare_postgres_urls_pin_the_installed_driver(raw):
    url = sqlalchemy_url(raw)
    assert url.drivername == POSTGRES_DRIVER
    assert (url.username, url.password, url.host, url.port, url.database) == (
        "ezop",
        "secret",
        "localhost",
        5432,
        "ezop",
    )


def test_explicit_driver_is_kept():
    assert sqlalchemy_url("postgresql+psycopg://u:p@h/db").drivername == "postgresql+psycopg"


def test_engine_uses_psycopg2_regardless_of_sqlalchemy_default():
    # SQLAlchemy 2.1 defaults bare postgresql:// to psycopg (v3), which requirements.txt does not install.
    engine = create_engine(sqlalchemy_url("postgresql://u:p@localhost/db"))
    assert engine.dialect.driver == "psycopg2"
