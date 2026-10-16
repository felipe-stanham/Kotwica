"""Watch job (flow-02): DNS and TLS results land in State and persist."""
import asyncio

from kotwica import health
from kotwica.host_watch import make_watch_job
from kotwica.state import StateStore
from tests.fixtures import NOW, PUBLIC_IP, make_config
from tests.test_tls_watch import cert_expiring_in

# The prod default is a single host now; these tests exercise several hosts sharing one hostname.
TWO_PORTS = {"PROD_WATCHED_HOSTS": "home.stanham.com:443,home.stanham.com:8443"}


def run_job(tmp_path, public_ip, answers, cert):
    config = make_config(**TWO_PORTS)
    store = StateStore(tmp_path / "state.json")
    store.state.public_ip, store.state.last_sync_at = public_ip, NOW
    store.state.reconcile_hosts(config.watched_hosts)
    job = make_watch_job(config, store, query=lambda r, h: answers, connect=lambda *a: cert, clock=lambda: NOW)
    asyncio.run(job())
    return config, store


def test_watch_job_updates_every_host_and_saves(tmp_path):
    config, store = run_job(tmp_path, PUBLIC_IP, [PUBLIC_IP], cert_expiring_in(40))
    assert store.state.last_watch_at == NOW
    assert [(h.dns_status, h.cert_status, h.days_left, h.checked_at) for h in store.state.hosts] == [("ok", "valid", 40, NOW)] * 2
    reloaded = StateStore(tmp_path / "state.json").load()
    assert reloaded.hosts[1].port == 8443 and reloaded.hosts[1].resolutions[0].result == "match"


def test_watch_job_state_drives_health(tmp_path):
    config, store = run_job(tmp_path, PUBLIC_IP, [PUBLIC_IP], cert_expiring_in(10))
    store.state.record = None
    result = health.evaluate(store.state, make_config(GODADDY_API_TOKEN="x"), NOW)
    assert result["message"].endswith("cert expires in 10 days (+1 more)")


def test_watch_job_without_public_ip_leaves_dns_unknown(tmp_path):
    _, store = run_job(tmp_path, None, ["198.51.100.2"], cert_expiring_in(40))
    assert {h.dns_status for h in store.state.hosts} == {"unknown"}


def test_one_failing_host_does_not_sink_the_cycle(tmp_path):
    config = make_config(**TWO_PORTS)
    store = StateStore(tmp_path / "state.json")
    store.state.public_ip = PUBLIC_IP
    store.state.reconcile_hosts(config.watched_hosts)

    def connect(connect_host, port, hostname):
        if port == 8443:
            raise RuntimeError("boom")
        return cert_expiring_in(40)

    asyncio.run(make_watch_job(config, store, query=lambda r, h: [PUBLIC_IP], connect=connect, clock=lambda: NOW)())
    good, bad = store.state.hosts
    assert (good.cert_status, good.days_left) == ("valid", 40)
    assert bad.cert_status == "unreachable" and "RuntimeError" in bad.error
    assert store.state.last_watch_at == NOW
    assert StateStore(tmp_path / "state.json").load().hosts[0].cert_status == "valid"
