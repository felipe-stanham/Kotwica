"""Public IP detection (cap-004): two echo services, known only when both give the same IPv4."""
import asyncio
import ipaddress
import logging
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

ECHO_TIMEOUT_S = 5.0


@dataclass
class PublicIpResult:
    ip: Optional[str]
    reason: Optional[str] = None  # set when ip is None


async def _ask(client: httpx.AsyncClient, url: str) -> str:
    """Return the validated IPv4 from one echo service, or raise ValueError with a short reason."""
    name = urlparse(url).hostname or url
    try:
        response = await client.get(url, timeout=ECHO_TIMEOUT_S)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ValueError("echo %s failed: %s" % (name, exc.__class__.__name__))
    try:
        return str(ipaddress.IPv4Address(response.text.strip()))
    except ValueError:
        raise ValueError("echo %s returned an invalid IPv4 answer" % name)


async def detect_public_ip(client: httpx.AsyncClient, urls: List[str]) -> PublicIpResult:
    outcomes = await asyncio.gather(*(_ask(client, url) for url in urls), return_exceptions=True)
    failures = [str(o) for o in outcomes if isinstance(o, ValueError)]
    if failures:
        return PublicIpResult(None, failures[0])
    unexpected = [o for o in outcomes if isinstance(o, BaseException)]
    if unexpected:
        raise unexpected[0]
    if len(set(outcomes)) != 1:
        return PublicIpResult(None, "echo services disagree")
    return PublicIpResult(outcomes[0])
