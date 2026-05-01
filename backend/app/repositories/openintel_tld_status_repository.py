"""Repository for OpenINTEL verification status persisted per TLD.

Read-only helpers. The write path (``upsert_status``) lived here while the
legacy ``sync_openintel_tld`` use-case existed; it has been replaced by
``ingestion/orchestrator/pipeline._reconcile_openintel_status`` which
issues raw SQL upserts directly.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.openintel_tld_status import OpenintelTldStatus


class OpenintelTldStatusRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, tld: str) -> OpenintelTldStatus | None:
        return self.db.get(OpenintelTldStatus, tld)

    def list_for_tlds(self, tlds: list[str]) -> list[OpenintelTldStatus]:
        if not tlds:
            return []
        return (
            self.db.query(OpenintelTldStatus)
            .filter(OpenintelTldStatus.tld.in_(tlds))
            .all()
        )
