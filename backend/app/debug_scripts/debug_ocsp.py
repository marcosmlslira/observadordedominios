import ssl, socket
from cryptography import x509
from cryptography.x509 import ExtensionOID
from cryptography.x509 import ocsp as x509_ocsp
from cryptography.hazmat.primitives import hashes, serialization
import httpx

domain = "revoked.badssl.com"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

with socket.create_connection((domain, 443), timeout=10) as sock:
    with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
        cert_der = ssock.getpeercert(binary_form=True)

cert = x509.load_der_x509_certificate(cert_der)
print("Subject:", cert.subject.rfc4514_string())
print("Issuer:", cert.issuer.rfc4514_string())

try:
    aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
    for a in aia.value:
        print("AIA:", a.access_method._name, "->", a.access_location.value)
except Exception as e:
    print("AIA error:", e)

# Try fetching issuer cert
ocsp_url = None
issuer_url = None
try:
    aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
    for a in aia.value:
        if a.access_method == x509.AuthorityInformationAccessOID.OCSP:
            ocsp_url = a.access_location.value
        if a.access_method == x509.AuthorityInformationAccessOID.CA_ISSUERS:
            issuer_url = a.access_location.value
except Exception as e:
    print("AIA parse error:", e)

print("OCSP URL:", ocsp_url)
print("Issuer URL:", issuer_url)

if issuer_url:
    try:
        resp = httpx.get(issuer_url, timeout=5)
        print("Issuer fetch status:", resp.status_code, "len:", len(resp.content))
        issuer = x509.load_der_x509_certificate(resp.content)
        print("Issuer cert subject:", issuer.subject.rfc4514_string())
    except Exception as e:
        print("Issuer fetch error:", e)
