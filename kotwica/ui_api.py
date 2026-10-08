"""Latarnia UI resources (spec cap-009): projections of State. No HTML."""
import time
from typing import Callable, Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from kotwica import health
from kotwica.config import Config
from kotwica.state import State, StateStore

RESOURCES = ["status", "hosts", "updates"]


def _status(state: State, config: Config) -> List[dict]:
    result = health.evaluate(state, config, time.time())
    record = state.record
    return [{
        "id": 1,
        "health": result["health"],
        "message": result["message"],
        "public_ip": state.public_ip,
        "record_name": "%s.%s" % (record.name, record.domain) if record else None,
        "record_ip": record.ip if record else None,
        "record_ttl": record.ttl if record else None,
        "date_last_sync": state.last_sync_at,
        "date_last_watch": state.last_watch_at,
        "last_error": (record.error if record and record.error else None) or state.public_ip_error,
    }]


def _hosts(state: State, config: Config) -> List[dict]:
    return [{
        "id": h.id,
        "name": "%s:%d" % (h.hostname, h.port),
        "dns_status": h.dns_status,
        "cert_status": h.cert_status,
        "days_left": h.days_left,
        "date_cert_expires": h.cert_not_after,
        "date_checked": h.checked_at,
        "cert_issuer": h.cert_issuer,
        "last_error": h.error,
        "resolutions": [{"resolver": r.resolver, "result": r.result, "answer": r.answer} for r in h.resolutions],
    } for h in state.hosts]


def _updates(state: State, config: Config) -> List[dict]:
    newest_first = sorted(state.updates, key=lambda u: (u.created_at, u.id), reverse=True)
    return [{
        "id": u.id,
        "date_created": u.created_at,
        "old_ip": u.old_ip,
        "new_ip": u.new_ip,
        "old_ttl": u.old_ttl,
        "new_ttl": u.new_ttl,
        "outcome": u.outcome,
        "error": u.error,
    } for u in newest_first]


PROJECTIONS: Dict[str, Callable[[State, Config], List[dict]]] = {
    "status": _status,
    "hosts": _hosts,
    "updates": _updates,
}


def _not_found(message: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "not_found", "message": message})


def build_router(config: Config, store: StateStore) -> APIRouter:
    router = APIRouter()

    @router.get("/ui")
    async def ui():
        return RESOURCES

    @router.get("/api/{resource}")
    async def list_resource(resource: str):
        projection = PROJECTIONS.get(resource)
        if projection is None:
            return _not_found("Unknown resource '%s'" % resource)
        return projection(store.state, config)

    @router.get("/api/{resource}/{item_id}")
    async def get_item(resource: str, item_id: str):
        projection = PROJECTIONS.get(resource)
        if projection is None:
            return _not_found("Unknown resource '%s'" % resource)
        for item in projection(store.state, config):
            if str(item["id"]) == item_id:
                return item
        return _not_found("%s '%s' not found" % (resource, item_id))

    return router
