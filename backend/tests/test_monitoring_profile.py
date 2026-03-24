from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.monitored_brand_alias import MonitoredBrandAlias
from app.models.monitored_brand_domain import MonitoredBrandDomain
from app.services.monitoring_profile import (
    build_alias_inputs,
    build_domain_inputs,
    build_seed_rows,
    derive_brand_label,
)


def test_build_domain_inputs_for_multilevel_suffix() -> None:
    domains = build_domain_inputs(["gsuplementos.com.br"])

    assert len(domains) == 1
    assert domains[0].registrable_label == "gsuplementos"
    assert domains[0].public_suffix == "com.br"
    assert domains[0].hostname_stem == "gsuplementos.com"


def test_build_alias_inputs_keeps_primary_aliases_and_keywords() -> None:
    aliases = build_alias_inputs(
        primary_brand_name="Growth Suplementos",
        aliases=["growth", "growth"],
        phrases=["growth suplementos"],
        support_keywords=["suplementos", "whey"],
    )

    summary = {(item.alias_type, item.alias_normalized) for item in aliases}
    assert ("brand_primary", "growthsuplementos") in summary
    assert ("brand_alias", "growth") in summary
    assert ("brand_phrase", "growthsuplementos") in summary
    assert ("support_keyword", "suplementos") in summary
    assert ("support_keyword", "whey") in summary


def test_seed_rows_include_domain_and_alias_channels() -> None:
    now = datetime.now(timezone.utc)
    domain = MonitoredBrandDomain(
        id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        domain_name="gsuplementos.com.br",
        registrable_domain="gsuplementos.com.br",
        registrable_label="gsuplementos",
        public_suffix="com.br",
        hostname_stem="gsuplementos.com",
        is_primary=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    alias = MonitoredBrandAlias(
        id=uuid.uuid4(),
        brand_id=domain.brand_id,
        alias_value="Growth",
        alias_normalized="growth",
        alias_type="brand_alias",
        weight_override=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    seeds = build_seed_rows([domain], [alias])
    by_type = {(item["seed_type"], item["channel_scope"], item["seed_value"]) for item in seeds}

    assert ("domain_label", "registrable_domain", "gsuplementos") in by_type
    assert ("official_domain", "certificate_hostname", "gsuplementos.com.br") in by_type
    assert ("hostname_stem", "certificate_hostname", "gsuplementos.com") in by_type
    assert ("brand_alias", "associated_brand", "growth") in by_type


def test_derive_brand_label_prefers_official_domain_label() -> None:
    domains = build_domain_inputs(["listenx.com.br"])
    assert derive_brand_label("ListenX", domains) == "listenx"
