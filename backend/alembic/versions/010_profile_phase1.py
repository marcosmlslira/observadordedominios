"""Phase 1 monitoring profile enrichment on top of monitored_brand.

Revision ID: 010_profile_phase1
Revises: 009_tool_execution
Create Date: 2026-03-24
"""

from typing import Sequence, Union

from alembic import op

revision: str = "010_profile_phase1"
down_revision: Union[str, None] = "009_tool_execution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE monitored_brand
        ADD COLUMN IF NOT EXISTS primary_brand_name VARCHAR(253),
        ADD COLUMN IF NOT EXISTS noise_mode VARCHAR(16) NOT NULL DEFAULT 'standard',
        ADD COLUMN IF NOT EXISTS notes TEXT
    """)

    op.execute("""
        UPDATE monitored_brand
        SET primary_brand_name = CASE
            WHEN position('.' in brand_name) > 0
                THEN brand_label
            ELSE brand_name
        END
        WHERE primary_brand_name IS NULL
    """)

    op.execute("""
        ALTER TABLE monitored_brand
        ALTER COLUMN primary_brand_name SET NOT NULL
    """)

    op.execute("""
        CREATE TABLE monitored_brand_domain (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,
            domain_name VARCHAR(253) NOT NULL,
            registrable_domain VARCHAR(253) NOT NULL,
            registrable_label VARCHAR(228) NOT NULL,
            public_suffix VARCHAR(24) NOT NULL,
            hostname_stem VARCHAR(228),
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_brand_domain_name
        ON monitored_brand_domain (brand_id, domain_name)
    """)
    op.execute("""
        CREATE INDEX ix_brand_domain_primary
        ON monitored_brand_domain (brand_id, is_primary)
    """)

    op.execute("""
        CREATE TABLE monitored_brand_alias (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,
            alias_value VARCHAR(253) NOT NULL,
            alias_normalized VARCHAR(253) NOT NULL,
            alias_type VARCHAR(24) NOT NULL,
            weight_override DOUBLE PRECISION,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_brand_alias_value
        ON monitored_brand_alias (brand_id, alias_normalized, alias_type)
    """)
    op.execute("""
        CREATE INDEX ix_brand_alias_type
        ON monitored_brand_alias (brand_id, alias_type)
    """)

    op.execute("""
        CREATE TABLE monitored_brand_seed (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,
            source_ref_type VARCHAR(24) NOT NULL,
            source_ref_id UUID,
            seed_value VARCHAR(253) NOT NULL,
            seed_type VARCHAR(32) NOT NULL,
            channel_scope VARCHAR(32) NOT NULL,
            base_weight DOUBLE PRECISION NOT NULL,
            is_manual BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_brand_seed_unique
        ON monitored_brand_seed (brand_id, seed_value, seed_type, channel_scope)
    """)
    op.execute("""
        CREATE INDEX ix_brand_seed_channel
        ON monitored_brand_seed (brand_id, channel_scope, is_active)
    """)

    op.execute("""
        ALTER TABLE similarity_match
        ADD COLUMN IF NOT EXISTS matched_channel VARCHAR(32),
        ADD COLUMN IF NOT EXISTS matched_seed_id UUID,
        ADD COLUMN IF NOT EXISTS matched_seed_value VARCHAR(253),
        ADD COLUMN IF NOT EXISTS matched_seed_type VARCHAR(32),
        ADD COLUMN IF NOT EXISTS matched_rule VARCHAR(32),
        ADD COLUMN IF NOT EXISTS source_stream VARCHAR(32)
    """)

    op.execute("""
        INSERT INTO monitored_brand_domain (
            brand_id,
            domain_name,
            registrable_domain,
            registrable_label,
            public_suffix,
            hostname_stem,
            is_primary
        )
        SELECT
            id,
            lower(brand_name),
            lower(brand_name),
            split_part(lower(brand_name), '.', 1),
            substring(lower(brand_name) from '[^.]+\\.(.*)$'),
            CASE
                WHEN substring(lower(brand_name) from '[^.]+\\.(.*)$') LIKE '%.%'
                    THEN split_part(lower(brand_name), '.', 1) || '.' ||
                         split_part(substring(lower(brand_name) from '[^.]+\\.(.*)$'), '.', 1)
                ELSE NULL
            END,
            TRUE
        FROM monitored_brand
        WHERE position('.' in brand_name) > 0
          AND brand_name NOT LIKE '% %'
        ON CONFLICT (brand_id, domain_name) DO NOTHING
    """)

    op.execute("""
        INSERT INTO monitored_brand_alias (
            brand_id,
            alias_value,
            alias_normalized,
            alias_type
        )
        SELECT
            id,
            primary_brand_name,
            lower(regexp_replace(primary_brand_name, '[^a-z0-9]+', '', 'g')),
            'brand_primary'
        FROM monitored_brand
        ON CONFLICT (brand_id, alias_normalized, alias_type) DO NOTHING
    """)

    op.execute("""
        INSERT INTO monitored_brand_alias (
            brand_id,
            alias_value,
            alias_normalized,
            alias_type
        )
        SELECT
            mb.id,
            keyword_value,
            lower(regexp_replace(keyword_value, '[^a-z0-9]+', '', 'g')),
            'support_keyword'
        FROM monitored_brand mb
        CROSS JOIN LATERAL unnest(mb.keywords) AS keyword_value
        WHERE keyword_value <> ''
        ON CONFLICT (brand_id, alias_normalized, alias_type) DO NOTHING
    """)

    op.execute("""
        INSERT INTO monitored_brand_seed (
            brand_id,
            source_ref_type,
            source_ref_id,
            seed_value,
            seed_type,
            channel_scope,
            base_weight
        )
        SELECT
            brand_id,
            'official_domain',
            id,
            registrable_label,
            'domain_label',
            'registrable_domain',
            1.00
        FROM monitored_brand_domain
        ON CONFLICT (brand_id, seed_value, seed_type, channel_scope) DO NOTHING
    """)

    op.execute("""
        INSERT INTO monitored_brand_seed (
            brand_id,
            source_ref_type,
            source_ref_id,
            seed_value,
            seed_type,
            channel_scope,
            base_weight
        )
        SELECT
            brand_id,
            'official_domain',
            id,
            domain_name,
            'official_domain',
            'certificate_hostname',
            0.85
        FROM monitored_brand_domain
        ON CONFLICT (brand_id, seed_value, seed_type, channel_scope) DO NOTHING
    """)

    op.execute("""
        INSERT INTO monitored_brand_seed (
            brand_id,
            source_ref_type,
            source_ref_id,
            seed_value,
            seed_type,
            channel_scope,
            base_weight
        )
        SELECT
            brand_id,
            'official_domain',
            id,
            hostname_stem,
            'hostname_stem',
            'certificate_hostname',
            0.95
        FROM monitored_brand_domain
        WHERE hostname_stem IS NOT NULL
        ON CONFLICT (brand_id, seed_value, seed_type, channel_scope) DO NOTHING
    """)

    op.execute("""
        INSERT INTO monitored_brand_seed (
            brand_id,
            source_ref_type,
            source_ref_id,
            seed_value,
            seed_type,
            channel_scope,
            base_weight
        )
        SELECT
            brand_id,
            'alias',
            id,
            alias_normalized,
            CASE alias_type
                WHEN 'brand_primary' THEN 'brand_primary'
                WHEN 'brand_phrase' THEN 'brand_phrase'
                WHEN 'brand_alias' THEN 'brand_alias'
                ELSE 'support_keyword'
            END,
            CASE
                WHEN alias_type = 'brand_primary' THEN 'both'
                ELSE 'associated_brand'
            END,
            CASE alias_type
                WHEN 'brand_primary' THEN 0.90
                WHEN 'brand_phrase' THEN 0.80
                WHEN 'brand_alias' THEN 0.65
                ELSE 0.20
            END
        FROM monitored_brand_alias
        ON CONFLICT (brand_id, seed_value, seed_type, channel_scope) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE similarity_match
        DROP COLUMN IF EXISTS source_stream,
        DROP COLUMN IF EXISTS matched_rule,
        DROP COLUMN IF EXISTS matched_seed_type,
        DROP COLUMN IF EXISTS matched_seed_value,
        DROP COLUMN IF EXISTS matched_seed_id,
        DROP COLUMN IF EXISTS matched_channel
    """)

    op.execute("DROP TABLE IF EXISTS monitored_brand_seed")
    op.execute("DROP TABLE IF EXISTS monitored_brand_alias")
    op.execute("DROP TABLE IF EXISTS monitored_brand_domain")

    op.execute("""
        ALTER TABLE monitored_brand
        DROP COLUMN IF EXISTS notes,
        DROP COLUMN IF EXISTS noise_mode,
        DROP COLUMN IF EXISTS primary_brand_name
    """)
