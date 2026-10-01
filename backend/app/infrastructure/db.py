from collections.abc import Iterator
from datetime import datetime, timezone
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_uuid(value) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


class Base(DeclarativeBase):
    pass


def _make_engine(database_url: str):
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **kwargs)


_session_local: sessionmaker | None = None
_engine = None


def init_db(database_url: str | None = None) -> None:
    global _session_local, _engine
    settings = get_settings()
    url = database_url or settings.database_url
    _engine = _make_engine(url)
    _session_local = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def get_engine():
    if _engine is None:
        init_db()
    return _engine


def get_session_factory() -> sessionmaker:
    if _session_local is None:
        init_db()
    return _session_local


def session_scope() -> Session:
    return get_session_factory()()


def get_session() -> Iterator[Session]:
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def create_all() -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def drop_all() -> None:
    Base.metadata.drop_all(bind=get_engine())