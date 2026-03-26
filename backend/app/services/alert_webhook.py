"""Alert webhook dispatch — fire-and-forget POST to brand-configured URLs.

Called after each similarity scan cycle to notify brands of new
immediate_attention matches discovered since the last scan.

Payload follows a stable schema so consumer integrations (Slack, PagerDuty,
custom dashboards) can parse it without versioning gymnastics.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

# Hard cap on total matches included per webhook call
MAX_MATCHES_PER_PAYLOAD = 20
# HTTP timeout (connect + read) in seconds
WEBHOOK_TIMEOUT_S = 10.0


def _build_payload(
    brand_id: UUID,
    brand_name: str,
    new_matches: list[dict],
    scan_completed_at: datetime,
) -> dict[str, Any]:
    """Build the structured webhook payload."""
    return {
        "event": "similarity.new_threats_detected",
        "schema_version": "1",
        "occurred_at": scan_completed_at.isoformat(),
        "brand": {
            "id": str(brand_id),
            "name": brand_name,
        },
        "summary": {
            "total_new": len(new_matches),
            "critical": sum(1 for m in new_matches if m.get("risk_level") == "critical"),
            "high": sum(1 for m in new_matches if m.get("risk_level") == "high"),
        },
        "matches": [
            {
                "domain": m.get("domain_name"),
                "risk_level": m.get("risk_level"),
                "disposition": m.get("disposition"),
                "attention_bucket": m.get("attention_bucket"),
                "actionability_score": m.get("actionability_score"),
                "recommended_action": m.get("recommended_action"),
                "first_detected_at": (
                    m["first_detected_at"].isoformat()
                    if isinstance(m.get("first_detected_at"), datetime)
                    else m.get("first_detected_at")
                ),
            }
            for m in new_matches[:MAX_MATCHES_PER_PAYLOAD]
        ],
    }


def dispatch_alert_webhook(
    webhook_url: str,
    brand_id: UUID,
    brand_name: str,
    new_matches: list[dict],
    scan_completed_at: datetime | None = None,
) -> bool:
    """POST a webhook notification. Returns True on 2xx, False otherwise.

    Non-blocking: errors are logged but never raised — a webhook failure
    must never abort the scan cycle or fail the worker.
    """
    if not new_matches:
        return True

    completed_at = scan_completed_at or datetime.now(timezone.utc)
    payload = _build_payload(brand_id, brand_name, new_matches, completed_at)

    try:
        with httpx.Client(timeout=WEBHOOK_TIMEOUT_S) as client:
            resp = client.post(webhook_url, json=payload)
        if resp.is_success:
            logger.info(
                "Webhook dispatched brand=%s url=%s status=%d matches=%d",
                brand_name, webhook_url, resp.status_code, len(new_matches),
            )
            return True
        else:
            logger.warning(
                "Webhook rejected brand=%s url=%s status=%d body=%.200s",
                brand_name, webhook_url, resp.status_code, resp.text,
            )
            return False
    except Exception:
        logger.exception(
            "Webhook dispatch failed brand=%s url=%s", brand_name, webhook_url
        )
        return False
