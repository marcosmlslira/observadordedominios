# backend/app/repositories/ingestion_config_repository.py
"""Repository for ingestion_source_config and ingestion_tld_policy tables."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.ingestion_source_config import IngestionSourceConfig
from app.models.ingestion_tld_policy import IngestionTldPolicy


class IngestionConfigRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Source config (cron) ─────────────────────────────────

    def get_config(self, source: str) -> IngestionSourceConfig | None:
        return self.db.get(IngestionSourceConfig, source)

    def list_configs(self) -> list[IngestionSourceConfig]:
        return (
            self.db.query(IngestionSourceConfig)
            .order_by(IngestionSourceConfig.source)
            .all()
        )

    def get_cron(self, source: str) -> str | None:
        """Return cron expression for source, or None if not found."""
        cfg = self.get_config(source)
        return cfg.cron_expression if cfg else None

    def upsert_cron(self, source: str, cron_expression: str) -> IngestionSourceConfig:
        now = datetime.now(timezone.utc)
        cfg = self.get_config(source)
        if cfg is None:
            cfg = IngestionSourceConfig(
                source=source,
                cron_expression=cron_expression,
                updated_at=now,
            )
            self.db.add(cfg)
        else:
            cfg.cron_expression = cron_expression
            cfg.updated_at = now
        self.db.flush()
        return cfg

    # ── TLD policy ───────────────────────────────────────────

    def list_tld_policies(self, source: str) -> list[IngestionTldPolicy]:
        return (
            self.db.query(IngestionTldPolicy)
            .filter(IngestionTldPolicy.source == source)
            .order_by(IngestionTldPolicy.tld)
            .all()
        )

    def get_tld_policy(self, source: str, tld: str) -> IngestionTldPolicy | None:
        return self.db.get(IngestionTldPolicy, (source, tld))

    def is_tld_enabled(self, source: str, tld: str) -> bool:
        """Return True if TLD is enabled (also True if no row exists — default-allow)."""
        policy = self.get_tld_policy(source, tld)
        return policy.is_enabled if policy is not None else True

    def ensure_tld(self, source: str, tld: str, *, is_enabled: bool = True) -> IngestionTldPolicy:
        """Get or create a TLD policy row."""
        policy = self.get_tld_policy(source, tld)
        if policy is None:
            policy = IngestionTldPolicy(
                source=source,
                tld=tld,
                is_enabled=is_enabled,
                updated_at=datetime.now(timezone.utc),
            )
            self.db.add(policy)
            self.db.flush()
        return policy

    def patch_tld(self, source: str, tld: str, *, is_enabled: bool) -> IngestionTldPolicy:
        policy = self.ensure_tld(source, tld)
        policy.is_enabled = is_enabled
        policy.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return policy

    def bulk_upsert_tlds(
        self,
        source: str,
        tld_states: list[dict],  # [{"tld": str, "is_enabled": bool}]
    ) -> list[IngestionTldPolicy]:
        """Upsert is_enabled for the supplied TLDs. Rows not in list are unchanged."""
        now = datetime.now(timezone.utc)
        for item in tld_states:
            policy = self.get_tld_policy(source, item["tld"])
            if policy is None:
                policy = IngestionTldPolicy(
                    source=source,
                    tld=item["tld"],
                    is_enabled=item["is_enabled"],
                    updated_at=now,
                )
                self.db.add(policy)
            else:
                policy.is_enabled = item["is_enabled"]
                policy.updated_at = now
        self.db.flush()
        return self.list_tld_policies(source)

    def list_enabled_tlds(self, source: str) -> list[str]:
        """Return sorted list of enabled TLD names for a source."""
        return [
            p.tld
            for p in self.list_tld_policies(source)
            if p.is_enabled
        ]
