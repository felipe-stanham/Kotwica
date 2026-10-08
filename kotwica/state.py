"""State dataclasses and the JSON-file StateStore (atomic writes)."""
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MAX_UPDATES = 50


@dataclass
class ManagedRecordState:
    name: str
    domain: str
    ip: Optional[str] = None
    ttl: Optional[int] = None
    last_sync_ok: bool = False
    error_kind: Optional[str] = None  # auth | missing | transient
    error: Optional[str] = None
    last_ok_update_at: Optional[int] = None


@dataclass
class Resolution:
    resolver: str
    result: str  # match | mismatch | nxdomain | failed
    answer: List[str] = field(default_factory=list)


@dataclass
class WatchedHostState:
    id: int
    hostname: str
    port: int
    dns_status: str = "unknown"  # ok | partial | wrong | unknown
    resolutions: List[Resolution] = field(default_factory=list)
    cert_status: Optional[str] = None  # valid | invalid | unreachable; None until first check
    cert_not_after: Optional[int] = None
    days_left: Optional[int] = None
    cert_issuer: Optional[str] = None
    error: Optional[str] = None
    checked_at: Optional[int] = None


@dataclass
class RecordUpdate:
    id: int
    created_at: int
    old_ip: Optional[str]
    new_ip: str
    old_ttl: Optional[int]
    new_ttl: int
    outcome: str  # ok | failed
    error: Optional[str] = None


@dataclass
class State:
    schema_version: int = SCHEMA_VERSION
    public_ip: Optional[str] = None
    public_ip_error: Optional[str] = None
    last_sync_at: Optional[int] = None
    last_watch_at: Optional[int] = None
    record: Optional[ManagedRecordState] = None
    hosts: List[WatchedHostState] = field(default_factory=list)
    updates: List[RecordUpdate] = field(default_factory=list)
    next_update_id: int = 1

    def add_update(self, update_without_id: dict) -> RecordUpdate:
        """Append a Record Update with the next id and keep only the most recent MAX_UPDATES."""
        update = RecordUpdate(id=self.next_update_id, **update_without_id)
        self.next_update_id += 1
        self.updates.append(update)
        del self.updates[:-MAX_UPDATES]
        return update

    def reconcile_hosts(self, watched_hosts: List[Tuple[str, int]]) -> None:
        """Rebuild hosts from config order, keeping known entries and dropping unconfigured ones."""
        known = {(h.hostname, h.port): h for h in self.hosts}
        rebuilt = []
        for index, (hostname, port) in enumerate(watched_hosts, start=1):
            host = known.get((hostname, port)) or WatchedHostState(id=index, hostname=hostname, port=port)
            host.id = index
            rebuilt.append(host)
        self.hosts = rebuilt


def _from_dict(data: dict) -> State:
    record = data.get("record")
    return State(
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        public_ip=data.get("public_ip"),
        public_ip_error=data.get("public_ip_error"),
        last_sync_at=data.get("last_sync_at"),
        last_watch_at=data.get("last_watch_at"),
        record=ManagedRecordState(**record) if record else None,
        hosts=[
            WatchedHostState(**{**h, "resolutions": [Resolution(**r) for r in h.get("resolutions", [])]})
            for h in data.get("hosts", [])
        ],
        updates=[RecordUpdate(**u) for u in data.get("updates", [])],
        next_update_id=data.get("next_update_id", 1),
    )


class StateStore:
    """Holds the State in memory and persists it to a JSON file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.state = State()

    def load(self) -> State:
        for leftover in self.path.parent.glob(".state-*.tmp"):  # left behind by a kill during save()
            leftover.unlink(missing_ok=True)
        try:
            data = json.loads(self.path.read_text())
            self.state = _from_dict(data)
        except FileNotFoundError:
            self.state = State()
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            log.warning("State file %s is unreadable (%s); starting with empty state", self.path, exc)
            self.state = State()
        return self.state

    def save(self) -> None:
        """Write the State atomically: temp file in the same directory, then rename over the target."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as tmp:
                json.dump(asdict(self.state), tmp, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise
