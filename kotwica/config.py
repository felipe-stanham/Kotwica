"""Environment config: process env > .env > committed per-env defaults."""
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Mapping, Optional, Tuple

from dotenv import dotenv_values

log = logging.getLogger(__name__)

TOKEN_KEY = "GODADDY_API_TOKEN"
SINGLE_WRITER_RECORD = "home"
RECORD_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
ENV_ALIASES = {"dev": "dev", "tst": "tst", "prd": "prod", "prod": "prod"}
PREFIXES = {"dev": "DEV_", "tst": "TST_", "prod": "PROD_"}

SHARED_DEFAULTS = {
    "domain": "stanham.com",
    "ttl": 600,
    "resolvers": ["8.8.8.8", "1.1.1.1"],
    "ip_echo_urls": ["https://api.ipify.org", "https://icanhazip.com"],
    "sync_interval_s": 300,
    "watch_interval_s": 900,
    "watched_hosts": "home.stanham.com:443,home.stanham.com:8443",
}

DEFAULTS = {
    "dev": {"managed_record": "kotwica-dev", "tls_connect_host": None, "log_level": "DEBUG"},
    "tst": {
        "managed_record": "home-tst",
        "watched_hosts": "home-tst.stanham.com:443",
        "tls_connect_host": "127.0.0.1",
        "log_level": "WARNING",
    },
    "prod": {"managed_record": "home", "tls_connect_host": "127.0.0.1", "log_level": "WARNING"},
}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    env: str
    domain: str
    managed_record: Optional[str]
    ttl: int
    watched_hosts: List[Tuple[str, int]]
    resolvers: List[str]
    ip_echo_urls: List[str]
    tls_connect_host: Optional[str]
    sync_interval_s: int
    watch_interval_s: int
    log_level: str
    port: int
    data_dir: Path
    godaddy_token: Optional[str] = field(default=None, repr=False)


def _split(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_hosts(value: str) -> List[Tuple[str, int]]:
    hosts = []
    for item in _split(value):
        hostname, sep, port = item.rpartition(":")
        if not sep or not hostname or not port.isdigit():
            raise ConfigError("invalid watched host %r, expected host:port" % item)
        if not 1 <= int(port) <= 65535:
            raise ConfigError("invalid port in watched host %r" % item)
        hosts.append((hostname, int(port)))
    if not hosts:
        raise ConfigError("no watched hosts configured")
    return hosts


def load(
    environ: Optional[Mapping[str, str]] = None,
    dotenv_path: Optional[Path] = None,
    port: int = 8150,
    data_dir: Path = Path("data"),
) -> Config:
    """Build the Config. Raises ConfigError for an unknown ENV or a violated single-writer guard."""
    environ = os.environ if environ is None else environ
    dotenv = dict(dotenv_values(dotenv_path)) if dotenv_path and Path(dotenv_path).is_file() else {}

    raw_env = (environ.get("ENV") or dotenv.get("ENV") or "dev").strip().lower()
    if raw_env not in ENV_ALIASES:
        raise ConfigError("unknown ENV %r (expected dev, tst or prd)" % raw_env)
    env = ENV_ALIASES[raw_env]
    prefix = PREFIXES[env]

    def pick(key: str) -> Optional[str]:
        for source in (environ, dotenv):
            value = source.get(prefix + key)
            if value is not None:
                return value
        return None

    defaults = DEFAULTS[env]

    def text(key: str, default):
        value = pick(key)
        return default if value is None else value

    managed_record = text("MANAGED_RECORD", defaults["managed_record"])
    if managed_record is not None:
        managed_record = managed_record.strip().lower()  # DNS names are case-insensitive
        if managed_record in ("", "none"):
            managed_record = None
    tls_connect_host = text("TLS_CONNECT_HOST", defaults["tls_connect_host"]) or None

    try:
        sync_interval_s = int(text("SYNC_INTERVAL_S", SHARED_DEFAULTS["sync_interval_s"]))
        watch_interval_s = int(text("WATCH_INTERVAL_S", SHARED_DEFAULTS["watch_interval_s"]))
    except ValueError as exc:
        raise ConfigError("interval must be an integer: %s" % exc)

    log_level = text("LOG_LEVEL", defaults["log_level"]).strip().upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ConfigError("invalid LOG_LEVEL %r" % log_level)

    token = (environ.get(TOKEN_KEY) or dotenv.get(prefix + TOKEN_KEY) or "").strip() or None

    if managed_record is not None and not RECORD_NAME.match(managed_record):
        raise ConfigError("invalid Managed Record name %r (single DNS label expected)" % managed_record)
    if managed_record == SINGLE_WRITER_RECORD and env != "prod":
        raise ConfigError(
            "single-writer guard: Managed Record %r may only be configured when ENV=prod (ENV=%s)"
            % (SINGLE_WRITER_RECORD, env)
        )

    echo_urls = _split(text("IP_ECHO_URLS", ",".join(SHARED_DEFAULTS["ip_echo_urls"])))
    if len(echo_urls) < 2:
        raise ConfigError("at least two IP echo services are required (they must agree)")

    return Config(
        env=env,
        domain=text("DOMAIN", SHARED_DEFAULTS["domain"]),
        managed_record=managed_record,
        ttl=SHARED_DEFAULTS["ttl"],
        watched_hosts=parse_hosts(text("WATCHED_HOSTS", defaults.get("watched_hosts") or SHARED_DEFAULTS["watched_hosts"])),
        resolvers=_split(text("RESOLVERS", ",".join(SHARED_DEFAULTS["resolvers"]))),
        ip_echo_urls=echo_urls,
        tls_connect_host=tls_connect_host,
        sync_interval_s=sync_interval_s,
        watch_interval_s=watch_interval_s,
        log_level=log_level,
        port=port,
        data_dir=Path(data_dir),
        godaddy_token=token,
    )
