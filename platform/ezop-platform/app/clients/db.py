import logging
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

# The driver installed by requirements.txt. A bare postgresql:// URL means psycopg2 on SQLAlchemy 2.0 but
# psycopg (v3) on 2.1+, so the driver is pinned here rather than left to the SQLAlchemy version.
POSTGRES_DRIVER = "postgresql+psycopg2"


def sqlalchemy_url(database_url: str) -> URL:
    """DATABASE_URL stays a plain postgresql:// URL (psql and Prisma read it too); pin the driver for SQLAlchemy."""
    url = make_url(database_url)
    if url.drivername in ("postgresql", "postgres"):
        url = url.set(drivername=POSTGRES_DRIVER)
    return url


@lru_cache
def _engine():
    settings = get_settings()
    logger.info("Initialising database engine")
    return create_engine(
        sqlalchemy_url(settings.database_url),
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )


def get_db() -> Generator[Session, None, None]:
    factory = sessionmaker(bind=_engine())
    db = factory()
    try:
        yield db
    finally:
        db.close()
