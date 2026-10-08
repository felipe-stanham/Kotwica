"""The watch job: DNS and TLS checks for every Watched Host (flow-02)."""
import asyncio
import logging
import time
from typing import Callable

from kotwica.config import Config
from kotwica.dns_watch import DnsQuery, check_dns, dns_query
from kotwica.scheduler import Job
from kotwica.state import StateStore, WatchedHostState
from kotwica.tls_watch import TlsConnect, check_tls, tls_connect

log = logging.getLogger(__name__)


def make_watch_job(
    config: Config,
    store: StateStore,
    query: DnsQuery = dns_query,
    connect: TlsConnect = tls_connect,
    clock: Callable[[], float] = time.time,
) -> Job:
    async def check_host(host: WatchedHostState, public_ip):
        try:
            await check_host_unsafe(host, public_ip)
        except Exception as exc:  # one bad host must not sink the cycle for the others
            log.exception("Watch of %s:%d failed", host.hostname, host.port)
            host.dns_status, host.resolutions = "unknown", []
            host.cert_status, host.error = "unreachable", "check failed: %s" % exc.__class__.__name__
            host.cert_not_after = host.days_left = host.cert_issuer = None
            host.checked_at = int(clock())

    async def check_host_unsafe(host: WatchedHostState, public_ip):
        # blocking dnspython and ssl calls run in worker threads
        dns_task = asyncio.to_thread(check_dns, host.hostname, public_ip, config.resolvers, query)
        tls_task = asyncio.to_thread(
            check_tls, host.hostname, host.port, config.tls_connect_host, clock(), connect
        )
        (dns_status, resolutions), cert = await asyncio.gather(dns_task, tls_task)
        host.dns_status, host.resolutions = dns_status, resolutions
        host.cert_status, host.cert_not_after = cert.status, cert.not_after
        host.days_left, host.cert_issuer, host.error = cert.days_left, cert.issuer, cert.error
        host.checked_at = int(clock())
        log.debug("Watched Host %s:%d dns=%s cert=%s", host.hostname, host.port, dns_status, cert.status)

    async def job() -> None:
        state = store.state
        await asyncio.gather(*(check_host(h, state.public_ip) for h in state.hosts))
        state.last_watch_at = int(clock())
        store.save()
        log.info("Watch cycle done for %d Watched Hosts", len(state.hosts))

    return job
