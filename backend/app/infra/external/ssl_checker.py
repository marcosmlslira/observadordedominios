"""SSL certificate checker using stdlib ssl + cryptography."""

from __future__ import annotations

import logging
import socket
import ssl
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509 import ocsp as x509_ocsp
from cryptography.x509.oid import ExtensionOID

import httpx

logger = logging.getLogger(__name__)

DEFAULT_PORT = 443
CONNECT_TIMEOUT = 10
OCSP_TIMEOUT = 5


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
                cert_der = ssock.getpeercert(binary_form=True)
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
                    "ocsp_status": _check_ocsp(cert_der) if cert_der else "unavailable",
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


def _check_ocsp(cert_der: bytes) -> str:
    """Check certificate revocation via OCSP. Returns: "good"|"revoked"|"unknown"|"unavailable"."""
    try:
        cert = x509.load_der_x509_certificate(cert_der)
    except Exception as exc:
        logger.debug("Failed to parse DER certificate: %s", exc)
        return "unavailable"

    ocsp_url = _extract_ocsp_url(cert)
    if not ocsp_url:
        return "unavailable"

    issuer_cert = _fetch_issuer_cert(cert)
    if not issuer_cert:
        return "unavailable"

    try:
        builder = x509_ocsp.OCSPRequestBuilder()
        builder = builder.add_certificate(cert, issuer_cert, hashes.SHA1())
        ocsp_request = builder.build()
        request_data = ocsp_request.public_bytes(serialization.Encoding.DER)
    except Exception as exc:
        logger.debug("Failed to build OCSP request: %s", exc)
        return "unavailable"

    try:
        resp = httpx.post(
            ocsp_url,
            content=request_data,
            headers={"Content-Type": "application/ocsp-request"},
            timeout=OCSP_TIMEOUT,
        )
        resp.raise_for_status()
        ocsp_response = x509_ocsp.load_der_ocsp_response(resp.content)
    except Exception as exc:
        logger.debug("OCSP request failed for %s: %s", ocsp_url, exc)
        return "unavailable"

    status = ocsp_response.certificate_status
    if status == x509_ocsp.OCSPCertStatus.GOOD:
        return "good"
    elif status == x509_ocsp.OCSPCertStatus.REVOKED:
        return "revoked"
    else:
        return "unknown"


def _extract_ocsp_url(cert: x509.Certificate) -> str | None:
    """Extract OCSP responder URL from authorityInfoAccess extension."""
    try:
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
        for access_desc in aia.value:
            if access_desc.access_method == x509.AuthorityInformationAccessOID.OCSP:
                return access_desc.access_location.value
    except x509.ExtensionNotFound:
        pass
    except Exception as exc:
        logger.debug("Failed to extract OCSP URL: %s", exc)
    return None


def _fetch_issuer_cert(cert: x509.Certificate) -> x509.Certificate | None:
    """Fetch issuer certificate via caIssuers AIA extension."""
    try:
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
        for access_desc in aia.value:
            if access_desc.access_method == x509.AuthorityInformationAccessOID.CA_ISSUERS:
                issuer_url = access_desc.access_location.value
                resp = httpx.get(issuer_url, timeout=OCSP_TIMEOUT)
                resp.raise_for_status()
                return x509.load_der_x509_certificate(resp.content)
    except x509.ExtensionNotFound:
        pass
    except Exception as exc:
        logger.debug("Failed to fetch issuer cert: %s", exc)
    return None
