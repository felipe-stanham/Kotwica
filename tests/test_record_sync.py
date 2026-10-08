"""cap-005 Managed Record sync (fakes) plus the [int] round trip on the dev record."""
import asyncio
import json
import logging

import httpx
import pytest

from kotwica import config as cfg
from kotwica import health
from kotwica.record_sync import make_sync_job
from kotwica.state import StateStore
from tests.conftest import ROOT
from tests.fakes import FakeWorld

IP = "203.0.113.7"
NOW = 1_800_000_000


def make(tmp_path, world, env=None):
    environ = {"ENV": "dev", "GODADDY_API_TOKEN": "tok-abc"}
    environ.update(env or {})
    config = cfg.load(environ=environ)
    store = StateStore(tmp_path / "state.json")
    store.state.last_watch_at = NOW  # only the sync job runs here; keep the "Starting" rule out of the way
    job = make_sync_job(config, store, world.factory(), clock=lambda: NOW)
    return config, store, job


def cycle(job):
    asyncio.run(job())


def test_sync_noop_when_equal(tmp_path):
    world = FakeWorld(record=[{"data": IP, "ttl": 600}])
    _, store, job = make(tmp_path, world)
    cycle(job)
    assert [r.method for r in world.godaddy] == ["GET"]
    assert store.state.updates == [] and store.state.record.ip == IP and store.state.record.last_sync_ok
    assert store.state.last_sync_at == NOW


def test_sync_updates_on_ip_change(tmp_path):
    world = FakeWorld(record=[{"data": "198.51.100.2", "ttl": 600}])
    config, store, job = make(tmp_path, world)
    cycle(job)
    puts = [r for r in world.godaddy if r.method == "PUT"]
    assert len(puts) == 1
    assert puts[0].url.path == "/v1/domains/stanham.com/records/A/kotwica-dev"
    assert json.loads(puts[0].content) == [{"data": IP, "ttl": 600}]
    assert puts[0].headers["Authorization"] == "Bearer tok-abc"
    (update,) = store.state.updates
    assert (update.old_ip, update.new_ip, update.outcome) == ("198.51.100.2", IP, "ok")
    assert store.state.record.last_ok_update_at == NOW


def test_sync_fixes_ttl(tmp_path):
    world = FakeWorld(record=[{"data": IP, "ttl": 3600}])
    _, store, job = make(tmp_path, world)
    cycle(job)
    assert json.loads([r for r in world.godaddy if r.method == "PUT"][0].content)[0]["ttl"] == 600
    assert (store.state.updates[0].old_ttl, store.state.updates[0].new_ttl) == (3600, 600)


def test_sync_missing_record(tmp_path):
    world = FakeWorld(record=[])
    config, store, job = make(tmp_path, world)
    cycle(job)
    assert [r.method for r in world.godaddy] == ["GET"]
    assert store.state.record.error_kind == "missing"
    result = health.evaluate(store.state, config, NOW)
    assert (result["health"], result["message"]) == ("error", "Managed Record kotwica-dev.stanham.com missing at GoDaddy")


def test_sync_auth_rejected(tmp_path):
    world = FakeWorld(get_status=401)
    config, store, job = make(tmp_path, world)
    cycle(job)
    assert [r.method for r in world.godaddy] == ["GET"] and store.state.record.error_kind == "auth"
    result = health.evaluate(store.state, config, NOW)
    assert result["health"] == "error" and result["message"].startswith("GoDaddy token rejected")


def test_sync_transient_then_retries(tmp_path):
    world = FakeWorld(get_status=503)
    config, store, job = make(tmp_path, world)
    cycle(job)
    assert store.state.record.error_kind == "transient"
    assert health.evaluate(store.state, config, NOW)["health"] == "warning"
    world.get_status, world.record = 200, [{"data": IP, "ttl": 600}]
    cycle(job)
    assert len(world.godaddy) == 2 and store.state.record.last_sync_ok and store.state.record.error_kind is None


def test_sync_put_fails(tmp_path):
    world = FakeWorld(record=[{"data": "198.51.100.2", "ttl": 600}], put_status=500)
    _, store, job = make(tmp_path, world)
    cycle(job)
    (update,) = store.state.updates
    assert update.outcome == "failed" and update.error
    assert store.state.record.error_kind == "transient" and store.state.record.last_ok_update_at is None


def test_sync_only_one_path_over_mixed_cycles(tmp_path):
    world = FakeWorld(record=[{"data": "198.51.100.2", "ttl": 600}])
    config, store, job = make(tmp_path, world)
    scenarios = [(200, 200), (503, 200), (401, 200), (200, 500), (403, 200), (200, 200), (429, 200), (200, 200), (500, 200), (200, 200)]
    for get_status, put_status in scenarios:
        world.get_status, world.put_status = get_status, put_status
        world.record = [{"data": "198.51.100.%d" % (len(world.requests) % 200), "ttl": 600}]
        cycle(job)
    assert world.godaddy
    for request in world.godaddy:
        assert request.method in ("GET", "PUT")
        assert request.url.path == "/v1/domains/stanham.com/records/A/" + config.managed_record


def test_ip_disagree_makes_no_godaddy_call(tmp_path):
    world = FakeWorld("203.0.113.7", "198.51.100.2", record=[{"data": IP, "ttl": 600}])
    config, store, job = make(tmp_path, world)
    cycle(job)
    assert world.godaddy == [] and store.state.public_ip is None and "disagree" in store.state.public_ip_error
    assert health.evaluate(store.state, config, NOW)["message"].startswith("Public IP undetectable")


def test_history_capped_at_50_most_recent(tmp_path):
    world = FakeWorld(record=[{"data": "198.51.100.2", "ttl": 600}])
    _, store, job = make(tmp_path, world)
    for i in range(60):
        ip = "203.0.113.%d" % (i + 1)
        world.echo = {"api.ipify.org": ip, "icanhazip.com": ip}
        world.record = [{"data": "198.51.100.2", "ttl": 600}]
        cycle(job)
    ids = [u.id for u in store.state.updates]
    assert len(ids) == 50 and ids == sorted(set(ids)) and ids[-1] == 60 and ids[0] == 11


def test_tst_is_watch_only_no_godaddy_request(tmp_path):
    world = FakeWorld(record=[{"data": "198.51.100.2", "ttl": 600}])
    config, store, job = make(tmp_path, world, env={"ENV": "tst", "GODADDY_API_TOKEN": ""})
    cycle(job)
    assert config.managed_record is None and world.godaddy == []
    assert store.state.public_ip == IP
    assert health.evaluate(store.state, config, NOW)["message"] != "GODADDY_API_TOKEN not set"


def test_missing_token_makes_no_godaddy_call(tmp_path):
    world = FakeWorld(record=[{"data": IP, "ttl": 600}])
    config, store, job = make(tmp_path, world, env={"GODADDY_API_TOKEN": ""})
    cycle(job)
    assert world.godaddy == []
    assert health.evaluate(store.state, config, NOW)["message"] == "GODADDY_API_TOKEN not set"


def test_token_never_logged_during_a_sync_cycle(tmp_path, caplog):
    world = FakeWorld(record=[{"data": "198.51.100.2", "ttl": 600}])
    _, store, job = make(tmp_path, world, env={"GODADDY_API_TOKEN": "gd_pat_SENTINEL123"})
    with caplog.at_level(logging.DEBUG):
        cycle(job)
        world.get_status = 401
        cycle(job)
    assert caplog.records and "SENTINEL123" not in caplog.text
    assert "secret-ish body" not in caplog.text and "secret-ish body" not in json.dumps(store.state.record.__dict__)


def test_two_records_under_the_name_are_collapsed_to_one(tmp_path):
    world = FakeWorld(record=[{"data": IP, "ttl": 600}, {"data": "198.51.100.9", "ttl": 600}])
    _, store, job = make(tmp_path, world)
    cycle(job)
    assert len([r for r in world.godaddy if r.method == "PUT"]) == 1


@pytest.mark.integration
def test_int_dev_record_roundtrip():
    """Needs the operator-created kotwica-dev.stanham.com (A 192.0.2.1, TTL 3600) and a dev token in .env."""
    config = cfg.load(environ={"ENV": "dev"}, dotenv_path=ROOT / ".env")
    assert config.env == "dev" and config.managed_record == "kotwica-dev"
    if not config.godaddy_token:
        pytest.skip("no DEV_GODADDY_API_TOKEN in .env: operator setup pending")

    import tempfile
    from pathlib import Path

    store = StateStore(Path(tempfile.mkdtemp()) / "state.json")
    job = make_sync_job(config, store)

    async def run():
        await job()
        first_puts = len(store.state.updates)
        await job()
        return first_puts, len(store.state.updates)

    first, second = asyncio.run(run())
    assert store.state.record.last_sync_ok, store.state.record.error
    assert store.state.record.ip == store.state.public_ip and store.state.record.ttl == 600
    assert second == first  # the second cycle produced no PUT


def test_failed_cycles_are_persisted_to_disk(tmp_path):
    world = FakeWorld(get_status=401)
    _, store, job = make(tmp_path, world)
    cycle(job)
    on_disk = StateStore(tmp_path / "state.json").load()
    assert on_disk.record.error_kind == "auth" and on_disk.last_sync_at == NOW


def test_crashing_sync_is_not_stamped_as_fresh(tmp_path):
    world = FakeWorld(record=[{"data": IP, "ttl": 600}])
    config, store, job = make(tmp_path, world)

    def boom(request):
        raise RuntimeError("unexpected")

    broken = make_sync_job(config, store, lambda: httpx.AsyncClient(transport=httpx.MockTransport(boom)), clock=lambda: NOW)
    with pytest.raises(RuntimeError):
        cycle(broken)
    assert store.state.last_sync_at is None


def test_unknown_domain_404_is_reported_as_missing_with_status(tmp_path):
    world = FakeWorld(get_status=404)
    _, store, job = make(tmp_path, world)
    cycle(job)
    assert store.state.record.error_kind == "missing" and "404" in store.state.record.error


def test_collapsing_extra_records_is_recorded_as_an_update(tmp_path):
    world = FakeWorld(record=[{"data": IP, "ttl": 600}, {"data": "198.51.100.9", "ttl": 600}])
    _, store, job = make(tmp_path, world)
    cycle(job)
    assert [(u.old_ip, u.new_ip, u.outcome) for u in store.state.updates] == [(IP, IP, "ok")]


@pytest.mark.parametrize("echo_a,echo_b", [
    (httpx.ReadTimeout("slow"), "203.0.113.7"),
    ("203.0.113.7", httpx.ConnectError("down")),
    ("<html>error</html>", "203.0.113.7"),
    ("2001:db8::1", "2001:db8::1"),
])
def test_unusable_echo_answers_make_no_godaddy_call(tmp_path, echo_a, echo_b):
    world = FakeWorld(echo_a, echo_b, record=[{"data": "198.51.100.2", "ttl": 600}])
    _, store, job = make(tmp_path, world)
    cycle(job)
    assert world.godaddy == [] and store.state.public_ip is None and store.state.updates == []


@pytest.mark.parametrize("get_status,put_status,kind", [
    (401, 200, "auth"), (403, 200, "auth"), (404, 200, "missing"), (429, 200, "transient"),
    (200, 401, "auth"), (200, 403, "auth"), (200, 429, "transient"),
])
def test_status_to_error_kind_on_get_and_put(tmp_path, get_status, put_status, kind):
    world = FakeWorld(record=[{"data": "198.51.100.2", "ttl": 600}], get_status=get_status, put_status=put_status)
    _, store, job = make(tmp_path, world)
    cycle(job)
    assert store.state.record.error_kind == kind
    for request in world.godaddy:
        assert request.headers["Authorization"] == "Bearer tok-abc"
