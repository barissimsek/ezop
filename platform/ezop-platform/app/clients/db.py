import logging
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _engine():
    settings = get_settings()
    logger.info("Initialising database engine")
    return create_engine(
        settings.database_url,
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
