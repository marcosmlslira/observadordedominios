"""Debug script: test LLM assessment generation with a mock match.

Usage:
    docker exec -it <container> python app/debug_scripts/test_llm_assessment.py
"""

import json
import sys

# Mock match data — simulates a phishing-suspicious domain
MOCK_MATCH = {
    "domain_name": "bradescoo",
    "tld": "com",
    "risk_level": "high",
    "attention_bucket": "immediate_attention",
    "score_final": 0.91,
    "actionability_score": 0.85,
    "matched_rule": "typo_candidate",
    "reasons": ["high_trigram_similarity", "brand_exact_substring"],
}

MOCK_BRAND_NAME = "Bradesco"

MOCK_TOOL_RESULTS = {
    "whois": {
        "status": "completed",
        "result": {
            "creation_date": "2025-11-10T00:00:00+00:00",
            "registrar": "NameCheap, Inc.",
            "registrant_country": "US",
        },
    },
    "dns_lookup": {
        "status": "completed",
        "result": {
            "records": [
                {"type": "A", "value": "104.21.0.1"},
                {"type": "MX", "value": "mail.bradescoo.com"},
            ],
            "nameservers": ["ns1.cloudflare.com"],
        },
    },
    "http_headers": {
        "status": "completed",
        "result": {
            "status_code": 200,
            "final_url": "https://bradescoo.com/login",
        },
    },
    "suspicious_page": {
        "status": "completed",
        "result": {
            "page_disposition": "live",
            "risk_level": "critical",
            "has_login_form": True,
            "has_credential_inputs": True,
        },
    },
    "email_security": {
        "status": "completed",
        "result": {
            "spoofing_risk": {"level": "critical"},
        },
    },
    "ip_geolocation": {
        "status": "completed",
        "result": {
            "country_code": "US",
            "org": "Cloudflare, Inc.",
            "asn": "AS13335",
        },
    },
}

MOCK_SIGNALS = [
    {"code": "recent_registration", "severity": "high", "description": "Domain registered in the last 30 days."},
    {"code": "credential_collection_surface", "severity": "critical", "description": "Login form detected."},
    {"code": "high_spoofing_risk", "severity": "high", "description": "Mail allows spoofing."},
]


def main():
    from app.core.config import settings  # noqa: imported here for clarity

    if not settings.OPENROUTER_API_KEY:
        print("[SKIP] OPENROUTER_API_KEY is not set — set it in environment to test.")
        sys.exit(0)

    from app.services.use_cases.generate_llm_assessment import (
        build_domain_summary,
        generate_llm_assessment,
        should_generate_assessment,
    )

    print("=== Gate check ===")
    gate = should_generate_assessment(MOCK_MATCH, settings.OPENROUTER_API_KEY)
    print(f"should_generate_assessment: {gate}")
    assert gate, "Gate should be True for high-risk match with API key"

    print("\n=== Domain summary ===")
    summary = build_domain_summary(MOCK_MATCH, MOCK_BRAND_NAME, MOCK_TOOL_RESULTS, MOCK_SIGNALS)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    print("\n=== LLM assessment (live call) ===")
    result = generate_llm_assessment(MOCK_MATCH, MOCK_BRAND_NAME, MOCK_TOOL_RESULTS, MOCK_SIGNALS)

    if result is None:
        print("[FAIL] generate_llm_assessment returned None — check logs above for error details.")
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n[OK] Assessment generated successfully.")


if __name__ == "__main__":
    main()
