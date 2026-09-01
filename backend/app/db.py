from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings, settings


def build_database_url(config: Settings) -> str | URL:
    """Return a connection target without interpolating credentials into a URL."""
    if config.database_url:
        return config.database_url
    if not config.postgres_password:
        raise RuntimeError(
            "Database configuration is incomplete: set POSTGRES_PASSWORD or DATABASE_URL"
        )
    return URL.create(
        drivername="postgresql+psycopg",
        username=config.postgres_user,
        password=config.postgres_password,
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_db,
    )


engine = create_engine(build_database_url(settings), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
