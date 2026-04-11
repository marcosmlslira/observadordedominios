"""Add priority column to ingestion_tld_policy for ordered execution.

Lower priority value = processed first. NULL = processed last (alphabetical within group).

Revision ID: 024_ingestion_tld_priority
Revises: 023_brand_domain_takeover_status
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "024_ingestion_tld_priority"
down_revision = "023_brand_domain_takeover_status"
branch_labels = None
depends_on = None

# Priority 1 — core high-value ccTLDs (phishing hotspots, large markets)
_P1_OPENINTEL = [
    "br", "fr", "de", "uk", "us",
    "nl", "it", "es", "eu", "ca",
    "au", "at", "be", "cz", "dk",
    "fi", "gr", "hu", "ie", "il",
    "jp", "kr", "mx", "no", "nz",
    "pl", "pt", "ro", "ru", "se",
    "sg", "tr", "tw", "ua", "za",
    "hk", "in", "id", "th", "ar",
    "co", "cl", "pe", "ch",
]

# Priority 2 — secondary ccTLDs with meaningful zone data
_P2_OPENINTEL = [
    "ac", "ae", "af", "ag", "al", "am", "ao", "ar", "as", "aw",
    "az", "ba", "bb", "bd", "bf", "bg", "bh", "bi", "bj", "bm",
    "bn", "bo", "bs", "bt", "bw", "by", "bz", "cc", "cd", "cf",
    "cg", "ci", "ck", "cl", "cm", "cn", "cr", "cu", "cv", "cw",
    "cx", "cy", "dj", "dm", "do", "dz", "ec", "ee", "eg", "er",
    "et", "fj", "fk", "fm", "fo", "ga", "gd", "ge", "gf", "gg",
    "gh", "gi", "gl", "gm", "gn", "gp", "gq", "gs", "gt", "gu",
    "gw", "gy", "hm", "hn", "hr", "ht", "im", "iq", "ir", "is",
    "je", "jm", "jo", "ke", "kg", "kh", "ki", "km", "kn", "kp",
    "kw", "ky", "kz", "la", "lb", "lc", "li", "lk", "lr", "ls",
    "lt", "lu", "lv", "ly", "ma", "mc", "md", "me", "mg", "mh",
    "mk", "ml", "mm", "mn", "mo", "mp", "mq", "mr", "ms", "mt",
    "mu", "mv", "mw", "my", "mz", "na", "nc", "ne", "nf", "ng",
    "ni", "np", "nr", "nu", "om", "pa", "pf", "pg", "ph", "pk",
    "pm", "pn", "pr", "ps", "pt", "pw", "py", "qa", "re", "rs",
    "rw", "sa", "sb", "sc", "sd", "sh", "si", "sk", "sl", "sm",
    "sn", "so", "sr", "ss", "st", "su", "sv", "sx", "sy", "sz",
    "tc", "td", "tf", "tg", "tj", "tk", "tl", "tm", "tn", "to",
    "tt", "tv", "tz", "ug", "uy", "uz", "va", "vc", "ve", "vg",
    "vi", "vn", "vu", "wf", "ws", "ye", "yt", "zm", "zw",
]

# xn-- IDN TLDs — lowest priority (priority 3), processed last
_P3_OPENINTEL_PREFIXES = ("xn--",)


def _build_priority_cases(tlds: list[str], priority: int) -> str:
    quoted = ", ".join(f"'{t}'" for t in tlds)
    return f"UPDATE ingestion_tld_policy SET priority = {priority} WHERE source = 'openintel' AND tld IN ({quoted});"


def upgrade() -> None:
    op.add_column(
        "ingestion_tld_policy",
        sa.Column("priority", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_ingestion_tld_policy_priority",
        "ingestion_tld_policy",
        ["source", "priority", "tld"],
    )

    # Seed priorities for openintel TLDs
    conn = op.get_bind()
    conn.execute(sa.text(_build_priority_cases(_P1_OPENINTEL, 1)))
    conn.execute(sa.text(_build_priority_cases(_P2_OPENINTEL, 2)))
    # IDN TLDs get priority 3
    conn.execute(
        sa.text(
            "UPDATE ingestion_tld_policy SET priority = 3 "
            "WHERE source = 'openintel' AND tld LIKE 'xn--%';"
        )
    )

    # Update default openintel cron to 13 UTC to match current DB value
    conn.execute(
        sa.text(
            "UPDATE ingestion_source_config SET cron_expression = '0 13 * * *', "
            "updated_at = now() WHERE source = 'openintel' AND cron_expression = '0 2 * * *';"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_tld_policy_priority", table_name="ingestion_tld_policy")
    op.drop_column("ingestion_tld_policy", "priority")
