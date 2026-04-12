"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infra.db.session import SessionLocal


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
