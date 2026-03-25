"""Repository for managing CZDS TLD policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.czds_tld_policy import CzdsTldPolicy


class CzdsPolicyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_enabled(self) -> list[CzdsTldPolicy]:
        now = datetime.now(timezone.utc)
        return (
            self.db.query(CzdsTldPolicy)
            .filter(CzdsTldPolicy.is_enabled == True)  # noqa: E712
            .filter(
                or_(
                    CzdsTldPolicy.suspended_until.is_(None),
                    CzdsTldPolicy.suspended_until <= now,
                )
            )
            .order_by(CzdsTldPolicy.priority.asc(), CzdsTldPolicy.tld.asc())
            .all()
        )

    def list_all(self) -> list[CzdsTldPolicy]:
        return (
            self.db.query(CzdsTldPolicy)
            .order_by(
                CzdsTldPolicy.is_enabled.desc(),
                CzdsTldPolicy.priority.asc(),
                CzdsTldPolicy.tld.asc(),
            )
            .all()
        )

    def replace_enabled_tlds(self, tlds: list[str]) -> list[CzdsTldPolicy]:
        now = datetime.now(timezone.utc)
        existing = {
            policy.tld: policy for policy in self.db.query(CzdsTldPolicy).all()
        }
        desired = set(tlds)

        for priority, tld in enumerate(tlds, start=1):
            policy = existing.get(tld)
            if policy is None:
                policy = CzdsTldPolicy(tld=tld)
                self.db.add(policy)

            policy.is_enabled = True
            policy.priority = priority
            policy.cooldown_hours = 24
            policy.failure_count = 0
            policy.last_error_code = None
            policy.last_error_at = None
            policy.suspended_until = None
            policy.notes = "Managed via admin ingestion settings"
            policy.updated_at = now

        for tld, policy in existing.items():
            if tld in desired:
                continue
            policy.is_enabled = False
            policy.updated_at = now

        self.db.flush()
        return self.list_enabled()

    def get(self, tld: str) -> CzdsTldPolicy | None:
        return self.db.get(CzdsTldPolicy, tld)

    def ensure(self, tld: str) -> CzdsTldPolicy:
        policy = self.get(tld)
        if policy is None:
            policy = CzdsTldPolicy(
                tld=tld,
                is_enabled=True,
                priority=999,
                cooldown_hours=24,
            )
            self.db.add(policy)
            self.db.flush()
        return policy

    def record_success(self, tld: str) -> CzdsTldPolicy:
        now = datetime.now(timezone.utc)
        policy = self.ensure(tld)
        policy.failure_count = 0
        policy.last_error_code = None
        policy.last_error_at = None
        policy.suspended_until = None
        policy.updated_at = now
        self.db.flush()
        return policy

    def record_failure(
        self,
        tld: str,
        *,
        status_code: int | None,
        message: str,
        suspend_hours: int | None = None,
    ) -> CzdsTldPolicy:
        now = datetime.now(timezone.utc)
        policy = self.ensure(tld)
        policy.failure_count = (policy.failure_count or 0) + 1
        policy.last_error_code = status_code
        policy.last_error_at = now
        policy.updated_at = now
        policy.notes = message
        if suspend_hours and suspend_hours > 0:
            policy.suspended_until = now + timedelta(hours=suspend_hours)
        self.db.flush()
        return policy
