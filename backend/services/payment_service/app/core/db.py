from shared.db import make_engine, make_session_factory
from .config import settings

engine = make_engine(settings.database_url)
SessionLocal = make_session_factory(engine)


def get_db():
    """Use as Depends(get_db, scope="function"): the session (and its pooled connection) is closed as soon as the
    endpoint returns, BEFORE FastAPI validates the response in another threadpool step. With the default request
    scope a finished request kept its connection while waiting for a thread, and under load every thread was
    waiting for a connection -> the service stalled for minutes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
