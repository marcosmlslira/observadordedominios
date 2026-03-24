"""Repository for managing CZDS TLD policy."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.czds_tld_policy import CzdsTldPolicy


class CzdsPolicyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_enabled(self) -> list[CzdsTldPolicy]:
        return (
            self.db.query(CzdsTldPolicy)
            .filter(CzdsTldPolicy.is_enabled == True)  # noqa: E712
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
            policy.notes = "Managed via admin ingestion settings"
            policy.updated_at = now

        for tld, policy in existing.items():
            if tld in desired:
                continue
            policy.is_enabled = False
            policy.updated_at = now

        self.db.flush()
        return self.list_enabled()
