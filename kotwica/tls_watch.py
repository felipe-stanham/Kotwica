"""TLS watch (cap-007): handshake with SNI and verification, read notAfter and issuer with stdlib ssl."""
import logging
import socket
import ssl
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger(__name__)

CONNECT_TIMEOUT_S = 10.0
MAX_REASON = 80

# (connect_host, port, server_hostname) -> getpeercert() dict; raises ssl.* / OSError
TlsConnect = Callable[[str, int, str], dict]


@dataclass
class CertResult:
    status: str  # valid | invalid | unreachable
    not_after: Optional[int] = None
    days_left: Optional[int] = None
    issuer: Optional[str] = None
    error: Optional[str] = None


def tls_connect(connect_host: str, port: int, server_hostname: str, timeout: float = CONNECT_TIMEOUT_S) -> dict:
    context = ssl.create_default_context()  # verifies chain and hostname
    with socket.create_connection((connect_host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=server_hostname) as tls:
            return tls.getpeercert()


def _issuer_cn(cert: dict) -> Optional[str]:
    fields = {key: value for rdn in cert.get("issuer", ()) for key, value in rdn}
    return fields.get("commonName") or fields.get("organizationName")


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_REASON else text[: MAX_REASON - 1] + "…"


def check_tls(
    hostname: str, port: int, connect_host: Optional[str], now: float, connect: TlsConnect = tls_connect
) -> CertResult:
    target = connect_host or hostname
    try:
        cert = connect(target, port, hostname)
    except ssl.SSLCertVerificationError as exc:
        return CertResult("invalid", error=_short(getattr(exc, "verify_message", "") or str(exc)))
    except ssl.SSLError as exc:  # e.g. Caddy answering with a TLS alert because it has no certificate
        return CertResult("invalid", error=_short(getattr(exc, "reason", "") or str(exc)))
    except OSError as exc:  # refused, reset, timeout, DNS failure
        return CertResult("unreachable", error=_short(str(exc) or exc.__class__.__name__))
    not_after = int(ssl.cert_time_to_seconds(cert["notAfter"]))
    return CertResult(
        "valid", not_after=not_after, days_left=int((not_after - now) // 86400), issuer=_issuer_cn(cert)
    )
