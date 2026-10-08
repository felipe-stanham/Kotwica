"""cap-003 scheduler and state store."""
import asyncio
import json
import logging
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

import app as app_module
from kotwica import config as cfg
from kotwica.scheduler import Scheduler
from kotwica.state import StateStore
from tests.conftest import ROOT


def test_intervals_respected():
    calls = {"sync": 0, "watch": 0}

    async def sync():
        calls["sync"] += 1

    async def watch():
        calls["watch"] += 1

    async def run():
        s = Scheduler(sync, watch, 2, 5)
        s.start()
        await asyncio.sleep(11)
        await s.stop()

    asyncio.run(run())
    assert abs(calls["sync"] - 6) <= 1
    assert abs(calls["watch"] - 3) <= 1


def test_job_failure_isolated(caplog):
    calls = {"sync": 0, "watch": 0}

    async def sync():
        calls["sync"] += 1

    async def watch():
        calls["watch"] += 1
        raise RuntimeError("boom")

    async def run():
        s = Scheduler(sync, watch, 0.2, 0.5)
        s.start()
        await asyncio.sleep(1.3)
        await s.stop()

    with caplog.at_level(logging.ERROR):
        asyncio.run(run())
    assert calls["sync"] >= 5
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and "watch" in r.getMessage()]
    assert len(errors) == calls["watch"]


def test_health_answers_while_job_fails(tmp_path):
    async def sync():
        pass

    async def watch():
        raise RuntimeError("boom")

    c = cfg.load(environ={"ENV": "dev"}, port=1, data_dir=tmp_path)
    with TestClient(app_module.create_app(c, StateStore(tmp_path / "s.json"), sync, watch)) as client:
        assert client.get("/health").status_code == 200


def test_state_survives_restart(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.state.add_update(dict(created_at=1, old_ip=None, new_ip="203.0.113.7", old_ttl=3600, new_ttl=600, outcome="ok"))
    store.save()
    next_id = store.state.next_update_id

    async def noop():
        pass

    restarted = StateStore(path)
    restarted.load()
    c = cfg.load(environ={"ENV": "dev"}, port=1, data_dir=tmp_path)
    with TestClient(app_module.create_app(c, restarted, noop, noop)):
        pass
    assert restarted.state.updates[0].new_ip == "203.0.113.7"
    assert restarted.state.next_update_id == next_id


def test_corrupt_state_loads_empty_with_warning(tmp_path, caplog):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    with caplog.at_level(logging.WARNING):
        state = StateStore(path).load()
    assert state.last_sync_at is None and state.updates == []
    assert any("state.json" in r.getMessage() for r in caplog.records)


def test_history_capped_ids_increase():
    store = StateStore("unused")
    for i in range(60):
        store.state.add_update(dict(created_at=i, old_ip=None, new_ip="1.1.1.1", old_ttl=None, new_ttl=600, outcome="ok"))
    ids = [u.id for u in store.state.updates]
    assert len(ids) == 50 and ids == sorted(set(ids)) and ids[-1] == 60


def test_reconcile_hosts_drops_unconfigured_and_numbers_by_order():
    store = StateStore("unused")
    store.state.reconcile_hosts([("a.example.com", 443), ("b.example.com", 443)])
    store.state.reconcile_hosts([("b.example.com", 443), ("c.example.com", 443)])
    assert [(h.id, h.hostname) for h in store.state.hosts] == [(1, "b.example.com"), (2, "c.example.com")]


WRITER = """
import sys
from kotwica.state import StateStore
store = StateStore(sys.argv[1])
print("ready", flush=True)
i = 0
while True:
    store.state.last_sync_at = i
    store.state.public_ip_error = "x" * 20000
    store.save()
    i += 1
"""


def test_atomic_write_survives_sigkill(tmp_path):
    path = tmp_path / "state.json"
    StateStore(path).save()
    for attempt in range(10):
        proc = subprocess.Popen([sys.executable, "-c", WRITER, str(path)], cwd=str(ROOT), stdout=subprocess.PIPE, text=True)
        proc.stdout.readline()
        time.sleep(0.05 + attempt * 0.013)
        proc.kill()
        proc.wait()
        json.loads(path.read_text())  # must always parse
