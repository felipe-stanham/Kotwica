"""cap-006 DNS watch."""
import dns.resolver
import pytest

from kotwica import dns_watch, health
from kotwica.dns_watch import check_dns
from tests.fixtures import NOW, PUBLIC_IP, healthy_state, make_config

RESOLVERS = ["8.8.8.8", "1.1.1.1"]


def fake_query(answers):
    """answers: resolver -> list of IPs, or an exception instance to raise."""
    calls = []

    def query(resolver, hostname):
        calls.append((resolver, hostname))
        outcome = answers[resolver]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    query.calls = calls
    return query


def test_dns_all_match():
    status, results = check_dns("home.stanham.com", PUBLIC_IP, RESOLVERS, fake_query({r: [PUBLIC_IP] for r in RESOLVERS}))
    assert status == "ok" and [r.result for r in results] == ["match", "match"]


def test_dns_partial():
    q = fake_query({"8.8.8.8": dns.resolver.NXDOMAIN(), "1.1.1.1": [PUBLIC_IP]})
    status, results = check_dns("home.stanham.com", PUBLIC_IP, RESOLVERS, q)
    assert status == "partial" and [r.result for r in results] == ["nxdomain", "match"]


def test_dns_wrong_and_health_error():
    q = fake_query({r: ["198.51.100.2"] for r in RESOLVERS})
    status, results = check_dns("home.stanham.com", PUBLIC_IP, RESOLVERS, q)
    assert status == "wrong"
    state = healthy_state()
    state.hosts = state.hosts[:1]
    state.hosts[0].dns_status, state.hosts[0].resolutions = status, results
    result = health.evaluate(state, make_config(), NOW)
    assert result["health"] == "error"
    assert result["message"] == "home.stanham.com resolves to 198.51.100.2, expected 203.0.113.7"


def test_dns_wrong_in_grace_is_warning():
    q = fake_query({r: ["198.51.100.2"] for r in RESOLVERS})
    status, results = check_dns("home.stanham.com", PUBLIC_IP, RESOLVERS, q)
    state = healthy_state()
    state.hosts = state.hosts[:1]
    state.hosts[0].dns_status, state.hosts[0].resolutions = status, results
    state.record.last_ok_update_at = NOW - 5 * 60
    result = health.evaluate(state, make_config(), NOW)
    assert result["health"] == "warning" and "propagating" in result["message"]


def test_dns_unknown_public_ip_makes_no_comparison_and_no_query():
    q = fake_query({r: ["198.51.100.2"] for r in RESOLVERS})
    status, results = check_dns("home.stanham.com", None, RESOLVERS, q)
    assert (status, results) == ("unknown", []) and q.calls == []
    state = healthy_state()
    state.hosts = state.hosts[:1]
    state.public_ip, state.public_ip_error = None, "echo services disagree"
    state.hosts[0].dns_status = status
    assert "resolves to" not in health.evaluate(state, make_config(), NOW)["message"]


def test_dns_all_resolvers_fail_is_unknown():
    q = fake_query({r: dns.resolver.LifetimeTimeout() for r in RESOLVERS})
    status, results = check_dns("home.stanham.com", PUBLIC_IP, RESOLVERS, q)
    assert status == "unknown" and {r.result for r in results} == {"failed"}


def test_dns_one_resolver_fails_other_matches_is_partial():
    q = fake_query({"8.8.8.8": RuntimeError("boom"), "1.1.1.1": [PUBLIC_IP]})
    assert check_dns("h", PUBLIC_IP, RESOLVERS, q)[0] == "partial"


def test_dns_resolvers_used_directly_not_system_resolver(monkeypatch):
    created = []

    class FakeResolver:
        def __init__(self, configure=True):
            self.configure = configure
            self.nameservers = None
            self.lifetime = None
            created.append(self)

        def resolve(self, name, rdtype):
            class Rec:
                address = PUBLIC_IP

            assert rdtype == "A"
            return [Rec()]

    monkeypatch.setattr(dns.resolver, "Resolver", FakeResolver)
    assert dns_watch.dns_query("8.8.8.8", "home.stanham.com") == [PUBLIC_IP]
    assert created[0].configure is False and created[0].nameservers == ["8.8.8.8"] and created[0].lifetime == 5.0


@pytest.mark.integration
def test_int_dns_real_lookup():
    status, results = check_dns("home.stanham.com", "203.0.113.7", RESOLVERS)
    assert {r.resolver for r in results} == set(RESOLVERS)
    assert all(r.result in ("match", "mismatch", "nxdomain", "failed") for r in results)


def test_dns_wrong_with_only_nxdomain_reads_as_no_record():
    q = fake_query({r: dns.resolver.NXDOMAIN() for r in RESOLVERS})
    status, results = check_dns("home.stanham.com", PUBLIC_IP, RESOLVERS, q)
    assert status == "wrong"
    state = healthy_state()
    state.hosts = state.hosts[:1]
    state.hosts[0].dns_status, state.hosts[0].resolutions = status, results
    assert health.evaluate(state, make_config(), NOW)["message"] == "home.stanham.com has no A record, expected 203.0.113.7"
