"""Test fixtures: isolated SQLite in-memory DB per test, TestClient, env before imports."""
import os

# Must be set before app modules are imported so config.settings resolves first.
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.models import Base
from app.seed import seed


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    Base.metadata.create_all(db_engine)
    session = sessionmaker(bind=db_engine, expire_on_commit=False)()
    seed(db=session)
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    import app.db as app_db
    import app.seed as seed_mod
    from app.main import app

    test_sessionmaker = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)
    # Rebind every module-level engine/session reference so lifespan's
    # create_all + seed() hit the test DB, never the configured Postgres.
    originals = (app_db.engine, app_db.SessionLocal, seed_mod.engine, seed_mod.SessionLocal)
    app_db.engine = db_engine
    app_db.SessionLocal = test_sessionmaker
    seed_mod.engine = db_engine
    seed_mod.SessionLocal = test_sessionmaker

    def override():
        session = sessionmaker(bind=db_engine, expire_on_commit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app, raise_server_exceptions=True) as c:  # lifespan seeds the test DB
            yield c
    finally:
        app.dependency_overrides.clear()
        (app_db.engine, app_db.SessionLocal, seed_mod.engine, seed_mod.SessionLocal) = originals
