"""Shared SQLAlchemy helpers (sync engine + PyMySQL; FastAPI runs `def` endpoints in a threadpool)."""
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def new_id() -> str:
    return str(uuid.uuid4())


def make_engine(url: str):
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20, pool_recycle=1800)


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
