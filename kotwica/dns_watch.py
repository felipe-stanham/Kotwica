"""DNS watch (cap-006): query each configured resolver directly and compare with the Public IP."""
import logging
from typing import Callable, List, Optional, Tuple

import dns.exception
import dns.resolver

from kotwica.state import Resolution

log = logging.getLogger(__name__)

# (resolver_ip, hostname) -> list of IPv4 strings; raises dns.* exceptions
DnsQuery = Callable[[str, str], List[str]]

QUERY_TIMEOUT_S = 5.0


def dns_query(resolver_ip: str, hostname: str, timeout: float = QUERY_TIMEOUT_S) -> List[str]:
    """A query sent straight to resolver_ip. Never the system resolver."""
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [resolver_ip]
    resolver.lifetime = timeout
    return [record.address for record in resolver.resolve(hostname, "A")]


def _classify(resolver_ip: str, hostname: str, public_ip: str, query: DnsQuery) -> Resolution:
    try:
        answer = query(resolver_ip, hostname)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return Resolution(resolver_ip, "nxdomain")
    except Exception as exc:  # timeout, refused, network: this resolver gave no usable answer
        log.debug("DNS query to %s for %s failed: %s", resolver_ip, hostname, exc.__class__.__name__)
        return Resolution(resolver_ip, "failed")
    return Resolution(resolver_ip, "match" if public_ip in answer else "mismatch", list(answer))


def check_dns(
    hostname: str, public_ip: Optional[str], resolvers: List[str], query: DnsQuery = dns_query
) -> Tuple[str, List[Resolution]]:
    """Return (dns_status, per-resolver results). Unknown Public IP means no comparison is made."""
    if public_ip is None:
        return "unknown", []
    results = [_classify(resolver, hostname, public_ip, query) for resolver in resolvers]
    outcomes = [r.result for r in results]
    if outcomes and all(o == "match" for o in outcomes):
        return "ok", results
    if "match" in outcomes:
        return "partial", results
    if any(o != "failed" for o in outcomes):
        return "wrong", results
    return "unknown", results
