"""Email security checks: SPF, DMARC, DKIM selectors via DNS TXT records."""

from __future__ import annotations

import logging
import re

import dns.resolver
import httpx

logger = logging.getLogger(__name__)

# Common DKIM selector names to probe
DKIM_SELECTORS = [
    "default", "google", "k1", "k2", "mail", "dkim", "selector1", "selector2",
    "s1", "s2", "smtp", "email", "mandrill", "mailjet", "sendgrid",
]


def _query_txt(name: str) -> list[str]:
    """Return all TXT record strings for a DNS name."""
    try:
        answers = dns.resolver.resolve(name, "TXT", lifetime=5)
        result = []
        for rdata in answers:
            for s in rdata.strings:
                result.append(s.decode("utf-8", errors="replace"))
        return result
    except Exception:
        return []


def _parse_spf(domain: str) -> dict:
    """Parse the SPF record for a domain."""
    txt_records = _query_txt(domain)
    spf_record = next((r for r in txt_records if r.startswith("v=spf1")), None)

    if not spf_record:
        return {
            "present": False,
            "record": None,
            "policy": None,
            "includes": [],
            "issues": ["No SPF record found — domain may be spoofed"],
        }

    issues = []
    policy = None
    includes = []

    # Extract qualifier
    if "~all" in spf_record:
        policy = "softfail"
    elif "-all" in spf_record:
        policy = "fail"
    elif "+all" in spf_record:
        policy = "pass_all"
        issues.append("SPF uses +all — allows any sender (very permissive)")
    elif "?all" in spf_record:
        policy = "neutral"
        issues.append("SPF uses ?all — neutral policy provides no protection")
    else:
        policy = "none"
        issues.append("SPF record has no 'all' qualifier")

    # Extract includes
    includes = re.findall(r"include:(\S+)", spf_record)

    # Check for too many lookups (DNS lookup limit is 10)
    lookup_mechanisms = re.findall(r"(?:include|redirect|a|mx|ptr|exists):", spf_record)
    if len(lookup_mechanisms) > 8:
        issues.append(f"SPF has {len(lookup_mechanisms)} DNS lookups (limit is 10)")

    return {
        "present": True,
        "record": spf_record,
        "policy": policy,
        "includes": includes,
        "issues": issues,
    }


def _parse_dmarc(domain: str) -> dict:
    """Parse the DMARC record for a domain."""
    dmarc_name = f"_dmarc.{domain}"
    txt_records = _query_txt(dmarc_name)
    dmarc_record = next((r for r in txt_records if r.startswith("v=DMARC1")), None)

    if not dmarc_record:
        return {
            "present": False,
            "record": None,
            "policy": None,
            "subdomain_policy": None,
            "percentage": None,
            "rua": None,
            "ruf": None,
            "issues": ["No DMARC record found — domain not protected against spoofing"],
        }

    issues = []

    # Parse policy
    p_match = re.search(r"p=(\w+)", dmarc_record)
    policy = p_match.group(1) if p_match else None
    if policy == "none":
        issues.append("DMARC policy is 'none' — monitoring only, no enforcement")
    elif policy not in ("quarantine", "reject"):
        issues.append(f"Unrecognized DMARC policy: {policy}")

    # Parse subdomain policy
    sp_match = re.search(r"sp=(\w+)", dmarc_record)
    subdomain_policy = sp_match.group(1) if sp_match else policy

    # Percentage
    pct_match = re.search(r"pct=(\d+)", dmarc_record)
    percentage = int(pct_match.group(1)) if pct_match else 100
    if percentage < 100:
        issues.append(f"DMARC applies to only {percentage}% of messages")

    # Reporting addresses
    rua_match = re.search(r"rua=([^;]+)", dmarc_record)
    ruf_match = re.search(r"ruf=([^;]+)", dmarc_record)
    rua = rua_match.group(1).strip() if rua_match else None
    ruf = ruf_match.group(1).strip() if ruf_match else None

    if not rua:
        issues.append("No aggregate reporting address (rua) configured")

    return {
        "present": True,
        "record": dmarc_record,
        "policy": policy,
        "subdomain_policy": subdomain_policy,
        "percentage": percentage,
        "rua": rua,
        "ruf": ruf,
        "issues": issues,
    }


def _check_dkim(domain: str) -> dict:
    """Probe common DKIM selectors and return found records."""
    found: list[dict] = []
    for selector in DKIM_SELECTORS:
        name = f"{selector}._domainkey.{domain}"
        records = _query_txt(name)
        dkim_record = next((r for r in records if "v=DKIM1" in r or "p=" in r), None)
        if dkim_record:
            found.append({"selector": selector, "record": dkim_record[:120] + "..." if len(dkim_record) > 120 else dkim_record})

    return {
        "found": len(found) > 0,
        "selectors_found": found,
        "selectors_checked": DKIM_SELECTORS,
    }


def _spoofing_risk_score(spf: dict, dmarc: dict, dkim: dict) -> dict:
    """Calculate an overall spoofing risk score (0-100, lower is better/safer)."""
    score = 0

    if not spf["present"]:
        score += 35
    elif spf["policy"] in ("pass_all", "neutral", "none"):
        score += 25
    elif spf["policy"] == "softfail":
        score += 10

    if not dmarc["present"]:
        score += 40
    elif dmarc["policy"] == "none":
        score += 25
    elif dmarc["policy"] == "quarantine":
        score += 10

    if not dkim["found"]:
        score += 25

    score = min(100, score)

    if score <= 15:
        level = "low"
    elif score <= 40:
        level = "medium"
    elif score <= 65:
        level = "high"
    else:
        level = "critical"

    return {"score": score, "level": level}


def _check_mta_sts(domain: str) -> dict:
    """Check MTA-STS policy.

    MTA-STS requer:
    1. TXT record em _mta-sts.<domain> com formato "v=STSv1; id=<policy_id>"
    2. Policy file em https://mta-sts.<domain>/.well-known/mta-sts.txt

    Returns:
        {
            "has_record": bool,
            "has_policy_file": bool,
            "mode": str | None,       # "enforce" | "testing" | "none"
            "policy_id": str | None,
        }
    """
    # 1. TXT record
    has_record = False
    policy_id = None
    txt_name = f"_mta-sts.{domain}"
    try:
        answers = dns.resolver.resolve(txt_name, "TXT", lifetime=5)
        for rdata in answers:
            for s in rdata.strings:
                decoded = s.decode("utf-8", errors="replace")
                if decoded.startswith("v=STSv1"):
                    has_record = True
                    for part in decoded.split(";"):
                        part = part.strip()
                        if part.startswith("id="):
                            policy_id = part[3:].strip()
                    break
    except Exception:
        pass

    # 2. Policy file
    has_policy_file = False
    mode = None
    policy_url = f"https://mta-sts.{domain}/.well-known/mta-sts.txt"
    try:
        resp = httpx.get(policy_url, timeout=5, follow_redirects=False)
        if resp.status_code == 200:
            has_policy_file = True
            for line in resp.text.splitlines():
                line = line.strip()
                if line.startswith("mode:"):
                    mode = line.split(":", 1)[1].strip().lower()
                    break
    except Exception:
        pass

    return {
        "has_record": has_record,
        "has_policy_file": has_policy_file,
        "mode": mode,
        "policy_id": policy_id,
    }


def check_email_security(domain: str) -> dict:
    """Run SPF, DMARC, and DKIM checks for a domain."""
    spf = _parse_spf(domain)
    dmarc = _parse_dmarc(domain)
    dkim = _check_dkim(domain)
    spoofing_risk = _spoofing_risk_score(spf, dmarc, dkim)

    mta_sts = _check_mta_sts(domain)

    return {
        "domain": domain,
        "spf": spf,
        "dmarc": dmarc,
        "dkim": dkim,
        "spoofing_risk": spoofing_risk,
        "mta_sts": mta_sts,
    }
