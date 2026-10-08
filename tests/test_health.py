"""cap-008 Health aggregation, evaluated against hand-built State fixtures."""
import dataclasses

from kotwica import health
from tests.fixtures import NOW, PUBLIC_IP, healthy_state, host, make_config

CONFIG = make_config()


def evaluate(state, config=CONFIG):
    return health.evaluate(state, config, NOW)


def test_health_good():
    result = evaluate(healthy_state())
    assert result["health"] == "good"
    assert result["message"] == "DNS 203.0.113.7 ok; certs 40+ days"


def test_health_priority():
    state = healthy_state([host(1, 443, dns="partial", days=10), host(2, 8443, dns="ok", days=60)])
    state.record.last_sync_ok, state.record.error_kind, state.record.error = False, "auth", "401"
    result = evaluate(state)
    assert result["health"] == "error"
    assert result["message"].startswith("GoDaddy token rejected")
    assert result["message"].endswith("(+2 more)")


def test_health_message_length():
    long_name = "h" * 120 + ".example.com"
    state = healthy_state([host(1, 443, hostname=long_name, cert="invalid", error="certificate has expired", days=None)])
    result = evaluate(state)
    assert result["health"] == "error"
    assert len(result["message"]) <= 100


def test_health_message_keeps_more_suffix_when_truncated():
    state = healthy_state([host(1, 443, hostname="h" * 120, cert="invalid", error="x", days=None),
                           host(2, 8443, hostname="g" * 10, dns="partial")])
    assert evaluate(state)["message"].endswith("(+1 more)")


def test_health_extra_info():
    info = evaluate(healthy_state())["extra_info"]
    for key in ("public_ip", "record_ip", "last_sync", "last_watch", "home.stanham.com:443", "home.stanham.com:8443"):
        assert key in info
    assert info["home.stanham.com:443"] == 40


def test_health_startup():
    state = healthy_state()
    state.last_sync_at = state.last_watch_at = None
    state.public_ip = state.record = None
    state.hosts = [dataclasses.replace(h, checked_at=None) for h in state.hosts]
    result = evaluate(state)
    assert (result["health"], result["message"]) == ("warning", "Starting: checks not completed yet")


def test_health_stale():
    state = healthy_state()
    state.last_sync_at = NOW - 20 * 60
    result = evaluate(state)
    assert result["health"] == "warning" and result["message"].startswith("Checks stale since")


def test_row2_missing_record():
    state = healthy_state()
    state.record.last_sync_ok, state.record.error_kind = False, "missing"
    assert evaluate(state)["message"] == "Managed Record home.stanham.com missing at GoDaddy"


def test_row3_token_missing_only_when_record_configured():
    no_token = make_config(GODADDY_API_TOKEN="")
    result = evaluate(healthy_state(), no_token)
    assert (result["health"], result["message"]) == ("error", "GODADDY_API_TOKEN not set")
    watch_only = make_config(ENV="tst", GODADDY_API_TOKEN="")
    assert evaluate(healthy_state(), watch_only)["health"] == "good"


def test_row4_tls_invalid_and_unreachable():
    state = healthy_state([host(1, 443, cert="invalid", error="certificate has expired", days=None)])
    assert evaluate(state)["message"] == "home.stanham.com:443 TLS invalid: certificate has expired"
    state = healthy_state([host(1, 443, cert="unreachable", error="connection refused", days=None)])
    assert evaluate(state)["message"] == "home.stanham.com:443 TLS unreachable: connection refused"


def test_cert_thresholds():
    assert evaluate(healthy_state([host(days=2)]))["message"] == "home.stanham.com:443 cert expires in 2 days"
    assert evaluate(healthy_state([host(days=2)]))["health"] == "error"
    assert evaluate(healthy_state([host(days=3)]))["health"] == "error"
    result = evaluate(healthy_state([host(days=10)]))
    assert (result["health"], result["message"]) == ("warning", "home.stanham.com:443 cert expires in 10 days")
    assert evaluate(healthy_state([host(days=14)]))["health"] == "warning"
    assert evaluate(healthy_state([host(days=15)]))["health"] == "good"


def test_row6_dns_wrong_outside_grace():
    state = healthy_state([host(dns="wrong", answers=["198.51.100.2"])])
    result = evaluate(state)
    assert result["health"] == "error"
    assert result["message"] == "home.stanham.com resolves to 198.51.100.2, expected 203.0.113.7"


def test_row10_dns_wrong_in_grace_is_propagating():
    state = healthy_state([host(dns="wrong", answers=["198.51.100.2"])])
    state.record.last_ok_update_at = NOW - 5 * 60
    result = evaluate(state)
    assert result["health"] == "warning" and "propagating" in result["message"]


def test_grace_expires_after_15_minutes():
    state = healthy_state([host(dns="wrong", answers=["198.51.100.2"])])
    state.record.last_ok_update_at = NOW - 16 * 60
    assert evaluate(state)["health"] == "error"


def test_row8_transient_and_row9_unknown_ip():
    state = healthy_state()
    state.record.last_sync_ok, state.record.error_kind, state.record.error = False, "transient", "HTTP 503"
    result = evaluate(state)
    assert (result["health"], result["message"]) == ("warning", "GoDaddy sync failed, retrying: HTTP 503")
    state = healthy_state()
    state.public_ip, state.public_ip_error = None, "echo services disagree"
    assert evaluate(state)["message"] == "Public IP undetectable: echo services disagree"


def test_row10_partial_names_disagreeing_resolver():
    assert evaluate(healthy_state([host(dns="partial")]))["message"] == "home.stanham.com: 8.8.8.8 disagrees"


def test_row11_unknown_dns_not_row6():
    state = healthy_state([host(dns="unknown")])
    state.public_ip, state.public_ip_error = None, "echo services disagree"
    result = evaluate(state)
    assert "resolves to" not in result["message"]
    assert result["health"] == "warning"
    assert evaluate(healthy_state([host(dns="unknown")]))["message"] == "home.stanham.com: DNS check inconclusive"


def test_shared_hostname_dns_problem_reported_once():
    state = healthy_state([host(1, 443, dns="partial"), host(2, 8443, dns="partial")])
    assert "more" not in evaluate(state)["message"]
