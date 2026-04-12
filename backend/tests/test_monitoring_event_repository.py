# backend/tests/test_monitoring_event_repository.py
"""Tests for MonitoringEventRepository."""
from __future__ import annotations
import sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import MagicMock
from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.models.monitoring_event import MonitoringEvent


def make_event(**kwargs):
    defaults = dict(
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        match_id=uuid.uuid4(),
        brand_domain_id=None,
        event_type="tool_execution",
        event_source="enrichment",
        tool_name="dns_lookup",
        result_data={"records": []},
    )
    defaults.update(kwargs)
    return defaults


def test_create_event_returns_model():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    repo = MonitoringEventRepository(db)
    evt = repo.create(**make_event())
    db.add.assert_called_once()
    assert isinstance(evt, MonitoringEvent)


def test_fetch_latest_for_match_tool():
    db = MagicMock()
    repo = MonitoringEventRepository(db)
    match_id = uuid.uuid4()
    result = repo.fetch_latest_for_match_tool(match_id=match_id, tool_name="dns_lookup")
    db.query.assert_called_once_with(MonitoringEvent)


def test_event_exists_for_cycle_returns_false_when_none():
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
    repo = MonitoringEventRepository(db)
    result = repo.event_exists_for_cycle(
        cycle_id=uuid.uuid4(),
        tool_name="dns_lookup",
        match_id=uuid.uuid4(),
    )
    assert result is False


def test_event_exists_for_cycle_returns_true_when_found():
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.first.return_value = MagicMock()
    repo = MonitoringEventRepository(db)
    result = repo.event_exists_for_cycle(
        cycle_id=uuid.uuid4(),
        tool_name="dns_lookup",
        match_id=uuid.uuid4(),
    )
    assert result is True
