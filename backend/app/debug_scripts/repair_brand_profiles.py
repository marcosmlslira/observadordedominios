"""Repair brand profiles — fix normalized labels and report duplicates.

Usage:
    docker exec -it <backend_container> python app/debug_scripts/repair_brand_profiles.py
    docker exec -it <backend_container> python app/debug_scripts/repair_brand_profiles.py --dry-run
"""
from __future__ import annotations

import sys
from app.infra.db.session import SessionLocal
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.services.use_cases.sync_monitoring_profile import ensure_monitoring_profile_integrity

DRY_RUN = "--dry-run" in sys.argv


def main() -> None:
    db = SessionLocal()
    try:
        repo = MonitoredBrandRepository(db)
        brands = repo.list_active()

        print(f"\n=== Brand Profile Repair Report {'(DRY RUN)' if DRY_RUN else ''} ===")
        print(f"Total active brands: {len(brands)}\n")

        fixes_applied = 0

        for brand in brands:
            old_label = brand.brand_label
            old_aliases = {a.alias_value: a.alias_normalized for a in brand.aliases}

            print(f"[{brand.brand_name}]  label={old_label!r}  seeds={len(brand.seeds)}")
            for alias in brand.aliases:
                from app.services.monitoring_profile import normalize_brand_text
                expected_norm = normalize_brand_text(alias.alias_value)
                mismatch = alias.alias_normalized != expected_norm
                flag = f"  ← WRONG (expected {expected_norm!r})" if mismatch else ""
                print(f"  alias [{alias.alias_type}]: {alias.alias_value!r} → stored={alias.alias_normalized!r}{flag}")

            if not DRY_RUN:
                ensure_monitoring_profile_integrity(repo, brand)
                db.commit()
                db.refresh(brand)

                new_label = brand.brand_label
                if new_label != old_label:
                    print(f"  ✓ brand_label repaired: {old_label!r} → {new_label!r}")
                    fixes_applied += 1

                for alias in brand.aliases:
                    old_norm = old_aliases.get(alias.alias_value)
                    if old_norm and old_norm != alias.alias_normalized:
                        print(f"  ✓ alias_normalized repaired: {alias.alias_value!r}: {old_norm!r} → {alias.alias_normalized!r}")
                        fixes_applied += 1

            print()

        print("=== Potential Duplicate Profiles ===")
        print("(Same base label, multiple profiles — consider deleting the one without official_domains)\n")

        labels: dict[str, list] = {}
        for brand in brands:
            # Normalize to base for grouping
            base = brand.brand_label
            for suffix in (".com.br", ".net.br", ".org.br", ".com", ".net", ".org"):
                base = base.replace(suffix, "")
            labels.setdefault(base, []).append(brand)

        found_duplicates = False
        for base, group in labels.items():
            if len(group) > 1:
                found_duplicates = True
                print(f"  Duplicate group '{base}':")
                for b in group:
                    has_official = bool(b.domains)
                    action = "KEEP" if has_official else "DELETE"
                    print(f"    [{action}] ID={b.id}  name={b.brand_name!r}  "
                          f"label={b.brand_label!r}  official_domains={has_official}  "
                          f"seeds={len(b.seeds)}")
                print()

        if not found_duplicates:
            print("  No duplicates found.")

        print(f"\n=== Summary ===")
        if DRY_RUN:
            print("  Dry run — no changes made. Run without --dry-run to apply fixes.")
        else:
            print(f"  Fixes applied: {fixes_applied}")
        print("  Done.\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
