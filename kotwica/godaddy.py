"""GoDaddy client: GET and PUT of exactly one A record. No other endpoint is ever called."""
import logging
from dataclasses import dataclass
from typing import List

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://api.godaddy.com"
TIMEOUT_S = 10.0


class GoDaddyError(Exception):
    kind = "transient"


class AuthError(GoDaddyError):
    kind = "auth"


class Missing(GoDaddyError):
    kind = "missing"


class Transient(GoDaddyError):
    kind = "transient"


@dataclass
class ARecord:
    ip: str
    ttl: int
    count: int = 1  # how many A records exist under this name


def _describe(response: httpx.Response) -> str:
    """Status code and GoDaddy's `code` field only; the body is never logged or stored."""
    code = None
    try:
        body = response.json()
        code = body.get("code") if isinstance(body, dict) else None
    except ValueError:
        pass
    return "HTTP %d (%s)" % (response.status_code, code) if code else "HTTP %d" % response.status_code


class GoDaddyClient:
    def __init__(self, client: httpx.AsyncClient, token: str, base_url: str = BASE_URL):
        self._client = client
        self._token = token
        self._base_url = base_url

    @staticmethod
    def _path(domain: str, name: str) -> str:
        return "/v1/domains/%s/records/A/%s" % (domain, name)

    async def _send(self, method: str, domain: str, name: str, **kwargs) -> httpx.Response:
        try:
            response = await self._client.request(
                method, self._base_url + self._path(domain, name),
                headers={"Authorization": "Bearer " + self._token, "Accept": "application/json"},
                timeout=TIMEOUT_S, **kwargs,
            )
        except httpx.HTTPError as exc:
            raise Transient("%s %s" % (method, exc.__class__.__name__))
        log.debug("GoDaddy %s %s -> %s", method, self._path(domain, name), _describe(response))
        if response.status_code in (401, 403):
            raise AuthError(_describe(response))
        if response.status_code == 404:
            raise Missing(_describe(response))
        if response.status_code >= 300:
            raise Transient(_describe(response))
        return response

    async def get_a(self, domain: str, name: str) -> ARecord:
        response = await self._send("GET", domain, name)
        try:
            records: List[dict] = response.json()
            first = records[0]
            return ARecord(ip=str(first["data"]), ttl=int(first["ttl"]), count=len(records))
        except IndexError:
            raise Missing("no A record %s.%s" % (name, domain))
        except (ValueError, KeyError, TypeError):
            raise Transient("unexpected GET response shape")

    async def put_a(self, domain: str, name: str, ip: str, ttl: int) -> None:
        await self._send("PUT", domain, name, json=[{"data": ip, "ttl": ttl}])
