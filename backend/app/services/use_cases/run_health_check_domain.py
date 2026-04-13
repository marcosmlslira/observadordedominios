"""Health check use case for one official brand domain.

Runs 10 monitoring tools, creates a monitoring_event per tool result,
then calls StateAggregator to recalculate brand_domain_health.
"""
from __future__ import annotations

import importlib
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.monitored_brand_domain import MonitoredBrandDomain
from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.services.state_aggregator import StateAggregator

logger = logging.getLogger(__name__)

# Tools run during health check, in order
_HEALTH_TOOLS: list[tuple[str, str]] = [
    ("dns_lookup",          "app.services.use_cases.tools.dns_lookup.DnsLookupService"),
    ("ssl_check",           "app.services.use_cases.tools.ssl_check.SslCheckService"),
    ("http_headers",        "app.services.use_cases.tools.http_headers.HttpHeadersService"),
    ("email_security",      "app.services.use_cases.tools.email_security.EmailSecurityService"),
    ("subdomain_takeover",  "app.services.use_cases.tools.subdomain_takeover_check.SubdomainTakeoverCheckService"),
    ("blacklist_check",     "app.services.use_cases.tools.blacklist_check.BlacklistCheckService"),
    ("safe_browsing",       "app.services.use_cases.tools.safe_browsing_check.SafeBrowsingCheckService"),
    ("urlhaus",             "app.services.use_cases.tools.urlhaus_check.UrlhausCheckService"),
    ("phishtank",           "app.services.use_cases.tools.phishtank_check.PhishTankCheckService"),
    ("suspicious_page",     "app.services.use_cases.tools.suspicious_page.SuspiciousPageService"),
]


def _run_tool(tool_class_path: str, domain: str) -> dict:
    """Import and instantiate a tool service, then execute it directly.

    Calls _execute() bypassing cache/rate-limit — health worker runs as an
    internal system job, not a user-facing API call.
    """
    module_path, class_name = tool_class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    service = getattr(module, class_name)()
    result = service._execute(domain)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "dict"):
        return result.dict()
    return result if isinstance(result, dict) else {}


def run_health_check_domain(
    db: Session,
    brand_domain: MonitoredBrandDomain,
    *,
    brand_id: UUID,
    organization_id: UUID,
    cycle_id: UUID,
) -> dict:
    """Run 10 health tools for one official brand domain.

    Creates one monitoring_event per tool. Skips tools already run
    for this cycle (idempotency). Calls StateAggregator after all tools.

    Returns:
        {"tools_run": int, "tools_failed": int, "overall_status": str}
    """
    domain_name = brand_domain.domain_name
    event_repo = MonitoringEventRepository(db)
    tools_run = 0
    tools_failed = 0

    for tool_name, tool_class_path in _HEALTH_TOOLS:
        # Idempotency: skip if already ran for this cycle + target
        if event_repo.event_exists_for_cycle(
            cycle_id=cycle_id,
            tool_name=tool_name,
            brand_domain_id=brand_domain.id,
        ):
            logger.debug(
                "Skipping %s for domain=%s (already in cycle)", tool_name, domain_name
            )
            tools_run += 1
            continue

        try:
            result_data = _run_tool(tool_class_path, domain_name)
            event_repo.create(
                organization_id=organization_id,
                brand_id=brand_id,
                brand_domain_id=brand_domain.id,
                cycle_id=cycle_id,
                event_type="tool_execution",
                event_source="health_check",
                tool_name=tool_name,
                result_data=result_data,
            )
            tools_run += 1
            logger.debug("health_check tool=%s domain=%s OK", tool_name, domain_name)
        except Exception:
            tools_failed += 1
            logger.exception(
                "health_check tool=%s domain=%s FAILED", tool_name, domain_name
            )
            # Record failure event so the aggregator knows the tool ran
            event_repo.create(
                organization_id=organization_id,
                brand_id=brand_id,
                brand_domain_id=brand_domain.id,
                cycle_id=cycle_id,
                event_type="tool_execution",
                event_source="health_check",
                tool_name=tool_name,
                result_data={"error": "tool_failed"},
            )

    db.commit()

    # Recalculate brand_domain_health from all recorded events
    aggregator = StateAggregator(db)
    aggregator.recalculate_domain_health(
        brand_domain_id=brand_domain.id,
        brand_id=brand_id,
        organization_id=organization_id,
    )
    # StateAggregator commits internally — no additional commit needed here

    from app.repositories.brand_domain_health_repository import BrandDomainHealthRepository
    health = BrandDomainHealthRepository(db).get_by_domain(brand_domain.id)
    overall_status = health.overall_status if health else "unknown"

    return {
        "tools_run": tools_run,
        "tools_failed": tools_failed,
        "overall_status": overall_status,
    }
