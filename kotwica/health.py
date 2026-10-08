"""Health Rules (spec cap-008): a pure function of (State, Config, now)."""
import time
from typing import Dict, List, Optional, Tuple

from kotwica.config import Config
from kotwica.state import State

MAX_MESSAGE = 100
GRACE_S = 15 * 60
ERROR_DAYS = 3
WARNING_DAYS = 14
STALE_FACTOR = 3

_RANK = {"good": 0, "warning": 1, "error": 2}


def _fmt(ts: Optional[int]) -> Optional[str]:
    return None if ts is None else time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts))


def _in_grace(state: State, now: float) -> bool:
    last_ok = state.record.last_ok_update_at if state.record else None
    return last_ok is not None and 0 <= now - last_ok < GRACE_S


def _matches(state: State, config: Config, now: float) -> List[Tuple[str, str]]:
    """Rows 1-13 in priority order, as (level, message). One entry per matching condition."""
    found: List[Tuple[str, str]] = []

    def add(level: str, message: str) -> None:
        # (+N more) counts distinct messages: two ports on one hostname report a DNS problem once
        if (level, message) not in found:
            found.append((level, message))

    record = state.record
    kind = record.error_kind if record and not record.last_sync_ok else None
    hosts = [h for h in state.hosts if h.checked_at is not None]

    if kind == "auth":
        add("error", "GoDaddy token rejected — renew GODADDY_API_TOKEN")
    if kind == "missing":
        add("error", "Managed Record %s.%s missing at GoDaddy" % (record.name, record.domain))
    if config.managed_record and not config.godaddy_token:
        add("error", "GODADDY_API_TOKEN not set")
    for h in hosts:
        if h.cert_status in ("invalid", "unreachable"):
            add("error", "%s:%d TLS %s: %s" % (h.hostname, h.port, h.cert_status, h.error or "no detail"))
    for h in hosts:
        if h.cert_status == "valid" and h.days_left is not None and h.days_left <= ERROR_DAYS:
            add("error", "%s:%d cert expires in %d days" % (h.hostname, h.port, h.days_left))
    grace = _in_grace(state, now)
    for h in hosts:
        if h.dns_status == "wrong" and not grace:
            answer = next((a for r in h.resolutions if r.result == "mismatch" for a in r.answer), None)
            if answer:
                add("error", "%s resolves to %s, expected %s" % (h.hostname, answer, state.public_ip))
            else:
                add("error", "%s has no A record, expected %s" % (h.hostname, state.public_ip))
    for h in hosts:
        if h.cert_status == "valid" and h.days_left is not None and ERROR_DAYS < h.days_left <= WARNING_DAYS:
            add("warning", "%s:%d cert expires in %d days" % (h.hostname, h.port, h.days_left))
    if kind == "transient":
        add("warning", "GoDaddy sync failed, retrying: %s" % (record.error or "no detail"))
    if state.last_sync_at is not None and state.public_ip is None:
        add("warning", "Public IP undetectable: %s" % (state.public_ip_error or "no detail"))
    for h in hosts:
        if h.dns_status == "partial":
            odd = next((r.resolver for r in h.resolutions if r.result != "match"), "a resolver")
            add("warning", "%s: %s disagrees" % (h.hostname, odd))
        elif h.dns_status == "wrong" and grace:
            add("warning", "%s: DNS propagating" % h.hostname)
    for h in hosts:
        if h.dns_status == "unknown":
            add("warning", "%s: DNS check inconclusive" % h.hostname)
    if state.last_sync_at is None or state.last_watch_at is None:
        add("warning", "Starting: checks not completed yet")
    stale = [
        ts for ts, interval in (
            (state.last_sync_at, config.sync_interval_s), (state.last_watch_at, config.watch_interval_s)
        )
        if ts is not None and now - ts > STALE_FACTOR * interval
    ]
    if stale:
        add("warning", "Checks stale since %s UTC" % _fmt(min(stale))[:16])
    return found


def _extra_info(state: State) -> Dict[str, object]:
    info: Dict[str, object] = {
        "public_ip": state.public_ip,
        "record_ip": state.record.ip if state.record else None,
        "last_sync": _fmt(state.last_sync_at),
        "last_watch": _fmt(state.last_watch_at),
    }
    for h in state.hosts:
        info["%s:%d" % (h.hostname, h.port)] = h.days_left if h.days_left is not None else (h.cert_status or "unchecked")
    return info


def _truncate(message: str, suffix: str) -> str:
    room = MAX_MESSAGE - len(suffix)
    if len(message) > room:
        message = message[: room - 1] + "…"
    return message + suffix


def evaluate(state: State, config: Config, now: float) -> dict:
    matches = _matches(state, config, now)
    if not matches:
        days = [h.days_left for h in state.hosts if h.days_left is not None]
        certs = "%d+ days" % min(days) if days else "ok"
        return {
            "health": "good",
            "message": "DNS %s ok; certs %s" % (state.public_ip, certs),
            "extra_info": _extra_info(state),
        }
    level = max((m[0] for m in matches), key=_RANK.__getitem__)
    suffix = " (+%d more)" % (len(matches) - 1) if len(matches) > 1 else ""
    return {"health": level, "message": _truncate(matches[0][1], suffix), "extra_info": _extra_info(state)}
