"""The sync job (flow-01): detect the Public IP and make the Managed Record match it."""
import logging
import time
from typing import Callable

import httpx

from kotwica.config import Config
from kotwica.godaddy import GoDaddyClient, GoDaddyError
from kotwica.public_ip import detect_public_ip
from kotwica.scheduler import Job
from kotwica.state import ManagedRecordState, StateStore

log = logging.getLogger(__name__)

ClientFactory = Callable[[], httpx.AsyncClient]


def _default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


def make_sync_job(
    config: Config,
    store: StateStore,
    client_factory: ClientFactory = _default_client,
    clock: Callable[[], float] = time.time,
) -> Job:
    def record_state() -> ManagedRecordState:
        state = store.state
        if state.record is None or (state.record.name, state.record.domain) != (config.managed_record, config.domain):
            state.record = ManagedRecordState(name=config.managed_record, domain=config.domain)
        return state.record

    def fail(record: ManagedRecordState, error: GoDaddyError) -> None:
        record.last_sync_ok, record.error_kind, record.error = False, error.kind, str(error)
        log.warning("Managed Record sync failed (%s): %s", error.kind, error)

    async def sync_record(http: httpx.AsyncClient, public_ip: str) -> None:
        record = record_state()
        godaddy = GoDaddyClient(http, config.godaddy_token)
        try:
            current = await godaddy.get_a(config.domain, config.managed_record)
        except GoDaddyError as exc:
            fail(record, exc)
            return
        record.ip, record.ttl = current.ip, current.ttl
        if current.ip == public_ip and current.ttl == config.ttl and current.count == 1:
            record.last_sync_ok, record.error_kind, record.error = True, None, None
            return
        update = dict(created_at=int(clock()), old_ip=current.ip, new_ip=public_ip,
                      old_ttl=current.ttl, new_ttl=config.ttl)
        try:
            await godaddy.put_a(config.domain, config.managed_record, public_ip, config.ttl)
        except GoDaddyError as exc:
            fail(record, exc)
            store.state.add_update({**update, "outcome": "failed", "error": str(exc)})
            return
        record.ip, record.ttl = public_ip, config.ttl
        record.last_sync_ok, record.error_kind, record.error = True, None, None
        record.last_ok_update_at = update["created_at"]
        store.state.add_update({**update, "outcome": "ok", "error": None})
        log.warning(
            "Record Update: %s.%s %s -> %s (ttl %s -> %s)",
            config.managed_record, config.domain, current.ip, public_ip, current.ttl, config.ttl,
        )

    async def job() -> None:
        state = store.state
        if config.managed_record:
            record_state()
        try:
            async with client_factory() as http:
                found = await detect_public_ip(http, config.ip_echo_urls)
                state.public_ip, state.public_ip_error = found.ip, found.reason
                if found.ip is None:
                    log.warning("Public IP undetectable: %s", found.reason)
                elif config.managed_record is None:
                    log.debug("No Managed Record configured: record sync skipped (watch-only)")
                elif not config.godaddy_token:
                    log.error("GODADDY_API_TOKEN not set: record sync skipped")
                else:
                    await sync_record(http, found.ip)
            state.last_sync_at = int(clock())  # only a cycle that ran to the end counts as "not stale"
        finally:
            store.save()

    return job
