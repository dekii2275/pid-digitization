"""SQLAlchemy database connection and session management."""

from __future__ import annotations

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import settings

# Engine configuration
# Note: For SQLite testing or PostgreSQL in development
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and ensure it closes after request completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
