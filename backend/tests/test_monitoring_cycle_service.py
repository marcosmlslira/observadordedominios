from __future__ import annotations
import sys, uuid
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock, call
from app.services.monitoring_cycle_service import MonitoringCycleService
from app.models.monitoring_cycle import MonitoringCycle


def make_cycle(**kwargs):
    c = MagicMock(spec=MonitoringCycle)
    c.id = uuid.uuid4()
    c.health_status = "pending"
    c.scan_status = "pending"
    c.enrichment_status = "pending"
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def test_begin_stage_updates_status_and_timestamp():
    db = MagicMock()
    cycle = make_cycle()
    repo = MagicMock()
    svc = MonitoringCycleService(db, cycle_repo=repo)
    svc.begin_stage(cycle.id, stage="health")
    repo.update_stage.assert_called_once()
    call_kwargs = repo.update_stage.call_args.kwargs
    assert call_kwargs["stage"] == "health"
    assert call_kwargs["status"] == "running"
    assert call_kwargs["started_at"] is not None


def test_finish_stage_updates_status_and_finished_at():
    db = MagicMock()
    cycle = make_cycle()
    repo = MagicMock()
    svc = MonitoringCycleService(db, cycle_repo=repo)
    svc.finish_stage(cycle.id, stage="health", success=True)
    call_kwargs = repo.update_stage.call_args.kwargs
    assert call_kwargs["status"] == "completed"
    assert call_kwargs["finished_at"] is not None


def test_finish_stage_marks_failed_on_error():
    db = MagicMock()
    repo = MagicMock()
    svc = MonitoringCycleService(db, cycle_repo=repo)
    svc.finish_stage(uuid.uuid4(), stage="enrichment", success=False)
    assert repo.update_stage.call_args.kwargs["status"] == "failed"
