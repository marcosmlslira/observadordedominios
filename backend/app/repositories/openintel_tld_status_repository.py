"""Repository for OpenINTEL verification status persisted per TLD."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Final

from sqlalchemy.orm import Session

from app.models.openintel_tld_status import OpenintelTldStatus

_UNSET: Final = object()


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

    def upsert_status(
        self,
        *,
        tld: str,
        last_probe_outcome: str | None = None,
        last_verification_at: datetime | None = None,
        last_available_snapshot_date: date | None | object = _UNSET,
        last_ingested_snapshot_date: date | None | object = _UNSET,
        last_error_message: str | None | object = _UNSET,
    ) -> OpenintelTldStatus:
        row = self.get(tld)
        if row is None:
            row = OpenintelTldStatus(tld=tld)
            self.db.add(row)

        row.last_probe_outcome = last_probe_outcome
        row.last_verification_at = last_verification_at or datetime.now(timezone.utc)

        if last_available_snapshot_date is not _UNSET:
            row.last_available_snapshot_date = last_available_snapshot_date
        if last_ingested_snapshot_date is not _UNSET:
            row.last_ingested_snapshot_date = last_ingested_snapshot_date
        if last_error_message is not _UNSET:
            row.last_error_message = last_error_message

        row.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return row
