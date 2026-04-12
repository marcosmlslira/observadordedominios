"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infra.db.session import SessionLocal, get_db


@pytest.fixture()
def db_session() -> Session:
    """
    Yields a real SQLAlchemy session connected to the running database.
    Rolls back all changes after the test so no data is left behind.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db_session: Session):
    """
    TestClient with DB session override and auth bypassed.
    Overrides get_db and get_current_admin so tests don't need JWT tokens.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.dependencies import get_current_admin

    def override_get_db():
        yield db_session

    def override_get_current_admin():
        return "admin@observador.com"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
