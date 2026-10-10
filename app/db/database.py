# Database Module
# SQLAlchemy engine, session management, and base models

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .core.config import settings

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE if hasattr(settings, 'DB_POOL_SIZE') else 10,
    max_overflow=settings.DB_MAX_OVERFLOW if hasattr(settings, 'DB_MAX_OVERFLOW') else 20,
    echo=settings.DEBUG,  # SQL logging in debug mode
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()