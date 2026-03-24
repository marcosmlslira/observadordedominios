"""SSL certificate checker using stdlib ssl + cryptography."""

from __future__ import annotations

import logging
import socket
import ssl
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_PORT = 443
CONNECT_TIMEOUT = 10


def check_ssl(domain: str, port: int = DEFAULT_PORT) -> dict:
    """Connect to domain:port via TLS, inspect the certificate chain.

    Returns a dict matching SslCheckResult schema.
    """
    issues: list[str] = []
    certificate: dict | None = None
    chain_length: int | None = None
    protocol_version: str | None = None
    cipher_suite: str | None = None
    is_valid = False

    ctx = ssl.create_default_context()

    try:
        with socket.create_connection((domain, port), timeout=CONNECT_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    issues.append("No certificate returned")
                    return {
                        "is_valid": False,
                        "certificate": None,
                        "chain_length": None,
                        "protocol_version": None,
                        "cipher_suite": None,
                        "issues": issues,
                    }

                is_valid = True
                protocol_version = ssock.version()
                cipher_info = ssock.cipher()
                cipher_suite = cipher_info[0] if cipher_info else None

                # Parse cert fields
                subject_parts = dict(x[0] for x in cert.get("subject", ()))
                issuer_parts = dict(x[0] for x in cert.get("issuer", ()))

                not_before_str = cert.get("notBefore", "")
                not_after_str = cert.get("notAfter", "")

                days_remaining = None
                if not_after_str:
                    try:
                        not_after_dt = datetime.strptime(
                            not_after_str, "%b %d %H:%M:%S %Y %Z"
                        ).replace(tzinfo=timezone.utc)
                        days_remaining = (not_after_dt - datetime.now(timezone.utc)).days
                        if days_remaining < 0:
                            issues.append("Certificate has expired")
                            is_valid = False
                        elif days_remaining < 30:
                            issues.append(f"Certificate expires in {days_remaining} days")
                    except ValueError:
                        pass

                san_list = []
                for san_type, san_value in cert.get("subjectAltName", ()):
                    if san_type == "DNS":
                        san_list.append(san_value)

                serial = cert.get("serialNumber")

                certificate = {
                    "subject": subject_parts.get("commonName"),
                    "issuer": issuer_parts.get("organizationName") or issuer_parts.get("commonName"),
                    "serial_number": serial,
                    "not_before": not_before_str,
                    "not_after": not_after_str,
                    "days_remaining": days_remaining,
                    "san": san_list,
                    "signature_algorithm": None,
                    "version": cert.get("version"),
                }

                # Chain length from peercert chain (approximation)
                chain_length = len(cert.get("caIssuers", [])) + 1

    except ssl.SSLCertVerificationError as exc:
        is_valid = False
        issues.append(f"Certificate verification failed: {exc}")
    except ssl.SSLError as exc:
        is_valid = False
        issues.append(f"SSL error: {exc}")
    except socket.timeout:
        issues.append("Connection timed out")
    except OSError as exc:
        issues.append(f"Connection failed: {exc}")

    return {
        "is_valid": is_valid,
        "certificate": certificate,
        "chain_length": chain_length,
        "protocol_version": protocol_version,
        "cipher_suite": cipher_suite,
        "issues": issues,
    }
