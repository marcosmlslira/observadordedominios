from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.config import settings
from app.services import tld_coverage


def test_resolve_tld_coverages_routes_non_czds_targets_to_ct(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TARGET_TLDS", "br,io,com")
    monkeypatch.setattr(settings, "CZDS_ENABLED_TLDS", "br,io,com")
    monkeypatch.setattr(settings, "CT_FALLBACK_INCLUDE_NON_CZDS", True)
    monkeypatch.setattr(settings, "CT_FALLBACK_PRIORITY_TLDS", "br,io")
    monkeypatch.setattr(settings, "CT_BR_SUBTLDS", "br,com.br,org.br")

    class DummyPolicyRepo:
        def __init__(self, db) -> None:
            self.db = db

        def list_all(self):
            return [
                SimpleNamespace(
                    tld="io",
                    last_error_code=403,
                    suspended_until=datetime.now(timezone.utc),
                )
            ]

    monkeypatch.setattr(tld_coverage, "CzdsPolicyRepository", DummyPolicyRepo)
    monkeypatch.setattr(tld_coverage, "get_authorized_czds_tlds", lambda czds_client=None: {"br", "com"})

    rows = {item.tld: item for item in tld_coverage.resolve_tld_coverages(db=object())}

    assert rows["com"].effective_source == "czds_primary"
    assert rows["com"].czds_available is True

    assert rows["br"].effective_source == "czds_primary"
    assert rows["br"].ct_enabled is False

    assert rows["io"].effective_source == "ct_fallback"
    assert rows["io"].czds_available is False
    assert rows["io"].ct_enabled is True
    assert rows["io"].fallback_reason == "czds_unavailable"
    assert rows["io"].priority_group == "priority"


def test_ct_fallback_helpers_expand_br_scope(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TARGET_TLDS", "br,io")
    monkeypatch.setattr(settings, "CZDS_ENABLED_TLDS", "br,io")
    monkeypatch.setattr(settings, "CT_FALLBACK_INCLUDE_NON_CZDS", True)
    monkeypatch.setattr(settings, "CT_FALLBACK_PRIORITY_TLDS", "br")
    monkeypatch.setattr(settings, "CT_BR_SUBTLDS", "br,com.br,net.br")
    monkeypatch.setattr(settings, "CT_STREAM_ENABLED_TLDS", "")

    class DummyPolicyRepo:
        def __init__(self, db) -> None:
            self.db = db

        def list_all(self):
            return []

    monkeypatch.setattr(tld_coverage, "CzdsPolicyRepository", DummyPolicyRepo)
    monkeypatch.setattr(tld_coverage, "get_authorized_czds_tlds", lambda czds_client=None: set())

    fallback_tlds = tld_coverage.resolve_ct_fallback_tlds(db=object())
    certstream_suffixes = tld_coverage.resolve_certstream_suffixes(db=object())

    assert fallback_tlds == ["com.br", "net.br", "io"]
    assert set(certstream_suffixes) == {".br", ".io"}


def test_target_tlds_expose_explicit_brazilian_second_level_domains(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TARGET_TLDS", "com,com.br,net.br,org.br,br")

    assert tld_coverage.get_target_tlds() == ["com", "com.br", "net.br", "org.br", "br"]


def test_get_authorized_czds_tlds_uses_short_lived_cache(monkeypatch) -> None:
    tld_coverage.clear_authorized_czds_tlds_cache()
    monkeypatch.setattr(settings, "CZDS_USERNAME", "user")
    monkeypatch.setattr(settings, "CZDS_PASSWORD", "pass")

    calls = {"count": 0}

    class DummyClient:
        def list_authorized_tlds(self):
            calls["count"] += 1
            return {"br", "com"}

    monkeypatch.setattr(tld_coverage, "CZDSClient", DummyClient)

    first = tld_coverage.get_authorized_czds_tlds()
    second = tld_coverage.get_authorized_czds_tlds()

    assert first == {"br", "com"}
    assert second == {"br", "com"}
    assert calls["count"] == 1

    tld_coverage.clear_authorized_czds_tlds_cache()
