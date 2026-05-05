from collections.abc import Generator

from sqlalchemy.orm import Session

from src.adapters.outbound.persistence.database import get_db
from src.config import Settings, settings


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_settings() -> Settings:
    return settings
