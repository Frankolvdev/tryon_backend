from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=max(settings.DATABASE_POOL_SIZE, 1),
    max_overflow=max(settings.DATABASE_MAX_OVERFLOW, 0),
    pool_timeout=max(settings.DATABASE_POOL_TIMEOUT_SECONDS, 1),
    pool_recycle=max(settings.DATABASE_POOL_RECYCLE_SECONDS, 60),
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()