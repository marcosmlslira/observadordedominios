"""Expand default CZDS TLD policy scope.

Revision ID: 008_expand_czds_tld_policy_defaults
Revises: 007_ct_br_partitions
Create Date: 2026-03-24

"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "008_expand_czds_tld_policy_defaults"
down_revision: Union[str, None] = "007_ct_br_partitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CZDS_DEFAULT_TLDS = [
    "com",
    "net",
    "org",
    "xyz",
    "online",
    "site",
    "store",
    "top",
    "info",
    "tech",
    "space",
    "website",
    "fun",
    "club",
    "vip",
    "icu",
    "live",
    "digital",
    "world",
    "today",
    "email",
    "solutions",
    "services",
    "support",
    "group",
    "company",
    "center",
    "zone",
    "agency",
    "systems",
    "network",
    "works",
    "tools",
    "io",
    "ai",
    "dev",
    "app",
    "cloud",
    "software",
    "co",
    "biz",
    "shop",
    "sale",
    "deals",
    "market",
    "finance",
    "financial",
    "money",
    "credit",
    "loan",
    "bank",
    "capital",
    "fund",
    "exchange",
    "trading",
    "pay",
    "cash",
    "us",
    "uk",
    "ca",
    "au",
    "de",
    "fr",
    "es",
    "it",
    "nl",
    "eu",
    "asia",
    "news",
    "media",
    "blog",
    "press",
    "link",
    "click",
    "one",
    "pro",
    "name",
    "life",
    "plus",
    "now",
    "global",
    "expert",
    "academy",
    "education",
    "school",
    "host",
    "hosting",
    "domains",
    "security",
    "safe",
    "protect",
    "chat",
    "social",
    "community",
    "team",
    "studio",
    "design",
    "marketing",
    "consulting",
    "partners",
    "ventures",
    "holdings",
    "international",
]


def upgrade() -> None:
    bind = op.get_bind()
    updated_at = datetime.now(timezone.utc)

    for priority, tld in enumerate(CZDS_DEFAULT_TLDS, start=1):
        bind.execute(
            sa.text(
                """
                INSERT INTO czds_tld_policy (
                    tld,
                    is_enabled,
                    priority,
                    cooldown_hours,
                    notes,
                    updated_at
                )
                VALUES (
                    :tld,
                    true,
                    :priority,
                    24,
                    'Managed default CZDS scope',
                    :updated_at
                )
                ON CONFLICT (tld) DO UPDATE
                SET
                    is_enabled = EXCLUDED.is_enabled,
                    priority = EXCLUDED.priority,
                    cooldown_hours = EXCLUDED.cooldown_hours,
                    notes = EXCLUDED.notes,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {"tld": tld, "priority": priority, "updated_at": updated_at},
        )

    allowed_tlds = ", ".join(f"'{tld}'" for tld in CZDS_DEFAULT_TLDS)
    bind.execute(
        sa.text(
            f"""
            UPDATE czds_tld_policy
            SET
                is_enabled = false,
                notes = 'Disabled by default CZDS scope refresh',
                updated_at = :updated_at
            WHERE tld NOT IN ({allowed_tlds})
            """
        ),
        {"updated_at": updated_at},
    )


def downgrade() -> None:
    bind = op.get_bind()
    updated_at = datetime.now(timezone.utc)

    bind.execute(
        sa.text(
            """
            UPDATE czds_tld_policy
            SET
                is_enabled = false,
                notes = 'Disabled by downgrade to phase-1 CZDS scope',
                updated_at = :updated_at
            WHERE tld NOT IN ('net', 'org', 'info')
            """
        ),
        {"updated_at": updated_at},
    )

    for priority, tld in enumerate(["net", "org", "info"], start=1):
        bind.execute(
            sa.text(
                """
                INSERT INTO czds_tld_policy (
                    tld,
                    is_enabled,
                    priority,
                    cooldown_hours,
                    notes,
                    updated_at
                )
                VALUES (
                    :tld,
                    true,
                    :priority,
                    24,
                    'Phase 1 - lightweight TLD',
                    :updated_at
                )
                ON CONFLICT (tld) DO UPDATE
                SET
                    is_enabled = EXCLUDED.is_enabled,
                    priority = EXCLUDED.priority,
                    cooldown_hours = EXCLUDED.cooldown_hours,
                    notes = EXCLUDED.notes,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {"tld": tld, "priority": priority, "updated_at": updated_at},
        )
