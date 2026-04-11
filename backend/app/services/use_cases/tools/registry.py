"""Register all available tool services."""

from __future__ import annotations

from app.api.v1.routers.tools import register_tool
from app.services.use_cases.tools.blacklist_check import BlacklistCheckService
from app.services.use_cases.tools.dns_lookup import DnsLookupService
from app.services.use_cases.tools.domain_similarity import DomainSimilarityService
from app.services.use_cases.tools.email_security import EmailSecurityService
from app.services.use_cases.tools.http_headers import HttpHeadersService
from app.services.use_cases.tools.ip_geolocation import IpGeolocationService
from app.services.use_cases.tools.reverse_ip import ReverseIpService
from app.services.use_cases.tools.screenshot_capture import ScreenshotCaptureService
from app.services.use_cases.tools.ssl_check import SslCheckService
from app.services.use_cases.tools.suspicious_page import SuspiciousPageService
from app.services.use_cases.tools.subdomain_takeover_check import SubdomainTakeoverCheckService
from app.services.use_cases.tools.website_clone import WebsiteCloneService
from app.services.use_cases.tools.whois_lookup import WhoisLookupService
from app.services.use_cases.tools.safe_browsing_check import SafeBrowsingCheckService


def register_all_tools() -> None:
    """Instantiate and register every tool service."""
    # Wave 1 — essential
    register_tool(DnsLookupService())
    register_tool(WhoisLookupService())
    register_tool(SslCheckService())
    register_tool(HttpHeadersService())
    register_tool(ScreenshotCaptureService())
    register_tool(SuspiciousPageService())
    # Wave 2 — enrichment
    register_tool(BlacklistCheckService())
    register_tool(EmailSecurityService())
    register_tool(ReverseIpService())
    register_tool(IpGeolocationService())
    register_tool(DomainSimilarityService())
    register_tool(WebsiteCloneService())
    register_tool(SubdomainTakeoverCheckService())
    register_tool(SafeBrowsingCheckService())
