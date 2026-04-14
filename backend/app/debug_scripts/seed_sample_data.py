"""Seed de dados de exemplo para o ambiente local.

Popula o banco com dados realistas para permitir desenvolvimento e teste
de funcionalidades sem precisar rodar os workers de ingestão.

Dados gerados:
  - ~1.000 domínios distribuídos em 3 TLDs (br, io, com)
  - 3 marcas monitoradas (bradesco, nubank, itau) com aliases e seeds
  - ~60 similarity matches com níveis de risco variados
  - Ingestion runs simulados (success / failed / running)
  - IngestionSourceConfig para os 3 workers

Uso:
    docker exec -it <backend_container> python app/debug_scripts/seed_sample_data.py
    docker exec -it <backend_container> python app/debug_scripts/seed_sample_data.py --clear
"""

from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.infra.db.session import SessionLocal
from app.models.ingestion_run import IngestionRun
from app.models.ingestion_source_config import IngestionSourceConfig
from app.models.monitored_brand import MonitoredBrand
from app.models.monitored_brand_alias import MonitoredBrandAlias
from app.models.monitored_brand_seed import MonitoredBrandSeed
from app.models.similarity_match import SimilarityMatch
from app.repositories.domain_repository import ensure_partition

CLEAR = "--clear" in sys.argv

# ── Constants ──────────────────────────────────────────────────────────────────

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime.now(timezone.utc)

SAMPLE_TLDS = ["br", "io", "com"]

BRANDS = [
    {
        "name": "bradesco",
        "label": "bradesco",
        "keywords": ["banco", "financeiro", "credito"],
        "variations": [
            "bradescc", "bradescco", "bradesco-bank", "bradesconet", "bradescoo",
            "bradescodigital", "bradescoseguro", "bradescoemprestimo", "bradesco24",
            "bradescoonline", "braadesco", "bradescobr", "mybradesco", "portalbradesco",
        ],
    },
    {
        "name": "nubank",
        "label": "nubank",
        "keywords": ["roxinho", "fintech", "cartao", "credito"],
        "variations": [
            "nubankbr", "nubank-digital", "nubankseguro", "nubank24h", "nubankapp",
            "nubankonline", "nu-bank", "nubankemprestimo", "meusnubank", "nubankpix",
            "nubankoficial", "nubank-cartao", "nubankfinanceiro", "nubankinvest",
        ],
    },
    {
        "name": "itau",
        "label": "itau",
        "keywords": ["banco", "unibanco", "financeiro", "credito"],
        "variations": [
            "itau-bank", "itaubr", "itaudigital", "itaunet", "itauseguro",
            "itaupersonalite", "itauonline", "itaupix", "itauemprestimo", "itauinvest",
            "itauoficial", "itauapp", "itaucartao", "itau24h",
        ],
    },
]

NOISE_DOMAINS = [
    "techsolutions", "cloudservices", "webmaster", "securepay", "fastdelivery",
    "globalnet", "smartlabs", "devstudio", "appdomain", "financetools",
    "investnow", "creditcheck", "paymentgate", "bankingpro", "loanservice",
    "moneyapp", "digitalwallet", "cryptotrade", "insurancepro", "realestate",
    "healthplus", "medicare", "pharmanet", "shophub", "retailpro",
    "logisticco", "transportnet", "fleetpro", "drivingapp", "carservice",
    "fooddelivery", "chefapp", "restaurantpro", "marketpro", "grocerynet",
    "academylearn", "educationhub", "schoolpro", "coursenet", "tutorapp",
    "travelclub", "flightpro", "hotelnet", "tourismapp", "vacationhub",
    "mediastream", "videonet", "musicpro", "gameclub", "sportshub",
]

RISK_LEVELS = ["low", "medium", "high", "critical"]
RISK_WEIGHTS = [0.3, 0.35, 0.25, 0.1]

ATTENTION_BUCKETS = ["urgent_review", "brand_hit", "keyword_match", "noise", None]

INGESTION_SOURCES = [
    ("czds", "0 7 * * *"),
    ("openintel", "0 2 * * *"),
    ("ct", "0 5 * * *"),
]

MATCH_STATUSES = ["new", "new", "new", "reviewing", "confirmed_threat", "dismissed"]
DISPOSITIONS = ["third_party", "threat", "legitimate", "parked", None]


# ── Helpers ────────────────────────────────────────────────────────────────────

def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def random_past_dt(max_days: int = 30) -> datetime:
    return NOW - timedelta(
        days=random.randint(0, max_days),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )


def normalize_label(value: str) -> str:
    return value.lower().replace("-", "").replace(".", "").replace("_", "")


# ── Clear ──────────────────────────────────────────────────────────────────────

def clear_seed_data(db) -> None:
    print("🧹 Limpando dados de seed anteriores...")
    db.execute(text("DELETE FROM similarity_match WHERE brand_id IN (SELECT id FROM monitored_brand WHERE organization_id = :oid)"), {"oid": str(ORG_ID)})
    db.execute(text("DELETE FROM monitored_brand WHERE organization_id = :oid"), {"oid": str(ORG_ID)})
    db.execute(text("DELETE FROM ingestion_run WHERE source IN ('czds_seed', 'openintel_seed', 'ct_seed')"))
    db.execute(text("DELETE FROM ingestion_source_config WHERE source LIKE '%_seed'"))
    for tld in SAMPLE_TLDS:
        db.execute(text(f"DELETE FROM domain WHERE tld = :tld"), {"tld": tld})
    db.commit()
    print("  ✅ Dados de seed removidos\n")


# ── Domains ────────────────────────────────────────────────────────────────────

def seed_domains(db) -> dict[str, list[str]]:
    """Insert sample domains. Returns {tld: [domain_name, ...]}."""
    print("🌐 Inserindo domínios de exemplo...")
    inserted: dict[str, list[str]] = {tld: [] for tld in SAMPLE_TLDS}

    for tld in SAMPLE_TLDS:
        ensure_partition(db, tld)

        labels: list[str] = []
        # brand variations
        for brand in BRANDS:
            labels.extend(brand["variations"])
        # noise
        labels.extend(NOISE_DOMAINS)
        # extra randoms to fill up to ~350 per TLD
        extras = [f"domain{i:04d}" for i in range(1, 280)]
        labels.extend(extras)

        for label in labels:
            name = f"{label}.{tld}"
            first_seen = random_past_dt(60)
            last_seen = first_seen + timedelta(days=random.randint(0, 10))
            try:
                db.execute(
                    text("""
                        INSERT INTO domain (name, tld, label, first_seen_at, last_seen_at)
                        VALUES (:name, :tld, :label, :first, :last)
                        ON CONFLICT (name, tld) DO NOTHING
                    """),
                    {"name": name, "tld": tld, "label": label, "first": first_seen, "last": last_seen},
                )
                inserted[tld].append(name)
            except Exception:
                db.rollback()

        db.commit()
        print(f"  ✅ TLD={tld}: {len(inserted[tld])} domínios inseridos")

    return inserted


# ── Brands ─────────────────────────────────────────────────────────────────────

def seed_brands(db) -> list[MonitoredBrand]:
    print("\n🏢 Inserindo marcas monitoradas...")
    brands_created: list[MonitoredBrand] = []

    for b in BRANDS:
        existing = db.execute(
            text("SELECT id FROM monitored_brand WHERE organization_id = :oid AND brand_name = :name"),
            {"oid": str(ORG_ID), "name": b["name"]},
        ).scalar()

        if existing:
            print(f"  ↩️  Marca '{b['name']}' já existe, pulando")
            brand = db.get(MonitoredBrand, existing)
            brands_created.append(brand)
            continue

        brand = MonitoredBrand(
            id=uuid.uuid4(),
            organization_id=ORG_ID,
            brand_name=b["name"],
            primary_brand_name=b["name"],
            brand_label=b["label"],
            keywords=b["keywords"],
            tld_scope=[],
            noise_mode="standard",
            is_active=True,
        )
        db.add(brand)
        db.flush()

        # Aliases
        alias = MonitoredBrandAlias(
            id=uuid.uuid4(),
            brand_id=brand.id,
            alias_value=b["name"],
            alias_normalized=normalize_label(b["name"]),
            alias_type="primary",
            is_active=True,
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(alias)

        # Seeds
        seed = MonitoredBrandSeed(
            id=uuid.uuid4(),
            brand_id=brand.id,
            source_ref_type="alias",
            source_ref_id=alias.id,
            seed_value=b["label"],
            seed_type="trigram",
            channel_scope="czds",
            base_weight=1.0,
            is_manual=False,
            is_active=True,
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(seed)

        brands_created.append(brand)
        print(f"  ✅ Marca '{b['name']}' criada")

    db.commit()
    return brands_created


# ── Similarity Matches ─────────────────────────────────────────────────────────

def seed_matches(db, brands: list[MonitoredBrand], domains_by_tld: dict[str, list[str]]) -> None:
    print("\n🔍 Inserindo similarity matches...")
    total = 0

    for brand_obj, brand_def in zip(brands, BRANDS):
        for tld in SAMPLE_TLDS:
            variations = brand_def["variations"]
            sample_count = min(len(variations), 7)
            sampled = random.sample(variations, sample_count)

            for label in sampled:
                domain_name = f"{label}.{tld}"
                first_seen = random_past_dt(30)
                score = round(random.uniform(0.55, 0.99), 3)
                risk = random.choices(RISK_LEVELS, weights=RISK_WEIGHTS)[0]
                actionability = round(random.uniform(0.1, 1.0), 3)

                existing = db.execute(
                    text("SELECT 1 FROM similarity_match WHERE brand_id = :bid AND domain_name = :dn"),
                    {"bid": str(brand_obj.id), "dn": domain_name},
                ).scalar()
                if existing:
                    continue

                match = SimilarityMatch(
                    id=uuid.uuid4(),
                    brand_id=brand_obj.id,
                    domain_name=domain_name,
                    tld=tld,
                    label=label,
                    score_final=score,
                    score_trigram=round(score * random.uniform(0.8, 1.0), 3),
                    score_levenshtein=round(score * random.uniform(0.7, 1.0), 3),
                    score_brand_hit=round(random.uniform(0.0, 1.0), 3),
                    score_keyword=round(random.uniform(0.0, 0.8), 3),
                    score_homograph=0.0,
                    actionability_score=actionability,
                    reasons=["trigram_match", "brand_substring"],
                    risk_level=risk,
                    attention_bucket=random.choice(ATTENTION_BUCKETS),
                    attention_reasons=["brand_in_label"] if risk in ("high", "critical") else None,
                    recommended_action="review" if risk in ("high", "critical") else "monitor",
                    enrichment_status="pending",
                    ownership_classification=random.choice(DISPOSITIONS),
                    self_owned=False,
                    disposition=random.choice(DISPOSITIONS),
                    delivery_risk=random.choice(["low", "medium", "high", None]),
                    first_detected_at=first_seen,
                    domain_first_seen=first_seen - timedelta(hours=random.randint(1, 72)),
                    status=random.choice(MATCH_STATUSES),
                    matched_channel="czds",
                    matched_seed_value=brand_def["label"],
                    matched_seed_type="trigram",
                    source_stream="czds",
                )
                db.add(match)
                total += 1

    db.commit()
    print(f"  ✅ {total} similarity matches inseridos")


# ── Ingestion Runs ─────────────────────────────────────────────────────────────

def seed_ingestion_runs(db) -> None:
    print("\n📋 Inserindo ingestion runs simulados...")
    total = 0

    run_templates = [
        # (source_tag, tld, status, days_ago_start, duration_minutes, domains_seen)
        ("czds", "br", "success", 1, 120, 5_800_000),
        ("czds", "io", "success", 1, 45, 320_000),
        ("czds", "com", "success", 2, 480, 175_000_000),
        ("czds", "net", "success", 2, 90, 14_000_000),
        ("czds", "br", "success", 8, 115, 5_750_000),
        ("czds", "com", "failed", 8, 30, 0),
        ("czds", "io", "success", 8, 42, 318_000),
        ("czds", "br", "success", 15, 118, 5_700_000),
        ("czds", "com", "success", 15, 470, 174_000_000),
        ("openintel", "br", "success", 1, 15, 4_900_000),
        ("openintel", "fr", "success", 1, 8, 3_200_000),
        ("openintel", "uk", "success", 2, 12, 10_500_000),
        ("openintel", "de", "success", 2, 11, 16_000_000),
        ("openintel", "br", "success", 8, 14, 4_850_000),
        ("ct", "br", "success", 0, 0, 12_500),
        ("ct", "com", "success", 0, 0, 48_000),
        ("ct", "io", "success", 1, 60, 8_900),
    ]

    for source, tld, status, days_back, duration_min, domains_seen in run_templates:
        source_tag = f"{source}_seed"
        started = days_ago(days_back).replace(hour=7, minute=0, second=0)
        finished = (started + timedelta(minutes=duration_min)) if duration_min > 0 else None

        run = IngestionRun(
            id=uuid.uuid4(),
            source=source_tag,
            tld=tld,
            status=status,
            started_at=started,
            finished_at=finished,
            domains_seen=domains_seen,
            domains_inserted=int(domains_seen * 0.003) if status == "success" else 0,
            domains_reactivated=int(domains_seen * 0.001) if status == "success" else 0,
            domains_deleted=int(domains_seen * 0.002) if status == "success" else 0,
            error_message="Connection timeout after 30 retries" if status == "failed" else None,
        )
        db.add(run)
        total += 1

    db.commit()
    print(f"  ✅ {total} ingestion runs inseridos")


# ── Source Config ──────────────────────────────────────────────────────────────

def seed_source_config(db) -> None:
    print("\n⚙️  Inserindo ingestion source config...")

    for source, cron in INGESTION_SOURCES:
        existing = db.execute(
            text("SELECT 1 FROM ingestion_source_config WHERE source = :s"),
            {"s": source},
        ).scalar()
        if not existing:
            cfg = IngestionSourceConfig(source=source, cron_expression=cron)
            db.add(cfg)

    db.commit()
    print("  ✅ Source configs inseridas")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    db = SessionLocal()
    try:
        if CLEAR:
            clear_seed_data(db)

        print("=" * 60)
        print("🌱 Seed de dados de exemplo — Observador de Domínios")
        print("=" * 60)

        domains_by_tld = seed_domains(db)
        brands = seed_brands(db)
        seed_matches(db, brands, domains_by_tld)
        seed_ingestion_runs(db)
        seed_source_config(db)

        total_domains = sum(len(v) for v in domains_by_tld.values())
        print("\n" + "=" * 60)
        print("✅ Seed concluído!")
        print(f"   Domínios:          {total_domains}")
        print(f"   Marcas:            {len(brands)}")
        print(f"   TLDs:              {', '.join(SAMPLE_TLDS)}")
        print("=" * 60)
        print("\nAcesse: http://localhost:3005")
        print("API:    http://localhost:8005/docs\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
