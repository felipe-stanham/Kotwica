"""Hand-built State and Config fixtures for health and UI tests."""
import time

from kotwica import config as cfg
from kotwica.state import ManagedRecordState, RecordUpdate, Resolution, State, WatchedHostState

NOW = 1_800_000_000
PUBLIC_IP = "203.0.113.7"


def make_config(**env):
    environ = {"ENV": "prd", "GODADDY_API_TOKEN": "tok"}
    environ.update(env)
    return cfg.load(environ=environ)


def host(id=1, port=443, hostname="home.stanham.com", dns="ok", days=60, cert="valid", error=None, answers=None):
    if answers is None:
        answers = [PUBLIC_IP]
    results = {"ok": ["match", "match"], "partial": ["nxdomain", "match"], "wrong": ["mismatch", "mismatch"],
               "unknown": ["failed", "failed"]}[dns]
    resolutions = [Resolution(r, res, [] if res in ("nxdomain", "failed") else list(answers))
                   for r, res in zip(["8.8.8.8", "1.1.1.1"], results)]
    return WatchedHostState(
        id=id, hostname=hostname, port=port, dns_status=dns, resolutions=resolutions, cert_status=cert,
        cert_not_after=NOW + days * 86400 if days is not None else None, days_left=days, cert_issuer="E6",
        error=error, checked_at=NOW - 60,
    )


def healthy_state(hosts=None):
    return State(
        public_ip=PUBLIC_IP, last_sync_at=NOW - 60, last_watch_at=NOW - 120,
        record=ManagedRecordState(name="home", domain="stanham.com", ip=PUBLIC_IP, ttl=600, last_sync_ok=True),
        hosts=hosts if hosts is not None else [host(1, 443, days=40), host(2, 8443, days=60)],
    )


def record_update(id, created_at, outcome="ok", old_ip="198.51.100.2", new_ip=PUBLIC_IP):
    return RecordUpdate(id=id, created_at=created_at, old_ip=old_ip, new_ip=new_ip, old_ttl=3600, new_ttl=600, outcome=outcome)
