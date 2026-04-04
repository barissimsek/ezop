import logging
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    ezop_port: int
    app_version: str
    log_level: str
    database_url: str

    def __init__(self) -> None:
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.app_version = os.getenv("GIT_TAG", "dev")
        self.ezop_port = int(os.getenv("EZOP_PORT") or os.getenv("PORT") or "8000")
        self.database_url = os.getenv("DATABASE_URL", "")

        if not self.database_url:
            raise RuntimeError("DATABASE_URL must be set.")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
