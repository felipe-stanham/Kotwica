"""cap-009 Latarnia UI resources and secret hygiene."""
import re

import pytest
from fastapi.testclient import TestClient

import app as app_module
from kotwica.state import StateStore
from tests.fixtures import NOW, healthy_state, make_config, record_update


async def _noop():
    pass


@pytest.fixture
def client(tmp_path):
    config = make_config(GODADDY_API_TOKEN="gd_pat_SENTINEL123")
    store = StateStore(tmp_path / "state.json")
    store.state = healthy_state()
    store.state.updates = [record_update(1, NOW - 300), record_update(2, NOW - 100), record_update(3, NOW - 200)]
    with TestClient(app_module.create_app(config, store, _noop, _noop)) as c:
        yield c


def test_ui_list(client):
    assert client.get("/ui").json() == ["status", "hosts", "updates"]


def test_api_status(client):
    body = client.get("/api/status").json()
    assert len(body) == 1 and body[0]["id"] == 1
    for key in ("health", "message", "public_ip", "record_name", "record_ip", "record_ttl",
                "date_last_sync", "date_last_watch", "last_error"):
        assert key in body[0]
    assert body[0]["record_name"] == "home.stanham.com"
    assert client.get("/api/status/1").json() == body[0]


def test_api_hosts(client):
    body = client.get("/api/hosts").json()
    assert [h["id"] for h in body] == [1, 2]
    assert body[0]["name"] == "home.stanham.com:443"
    for key in ("name", "dns_status", "cert_status", "days_left", "date_cert_expires", "date_checked",
                "cert_issuer", "last_error", "resolutions"):
        assert key in body[0]
    assert set(body[0]["resolutions"][0]) == {"resolver", "result", "answer"}


def test_api_updates_order(client):
    body = client.get("/api/updates").json()
    assert [u["date_created"] for u in body] == [NOW - 100, NOW - 200, NOW - 300]
    for key in ("id", "date_created", "old_ip", "new_ip", "old_ttl", "new_ttl", "outcome", "error"):
        assert key in body[0]


def test_api_item_by_id_and_404(client):
    assert client.get("/api/hosts/2").json()["name"] == "home.stanham.com:8443"
    missing = client.get("/api/hosts/99")
    assert missing.status_code == 404 and {"error", "message"} <= set(missing.json())
    assert client.get("/api/hosts/abc").status_code == 404
    assert client.get("/api/nothing").status_code == 404


def test_api_dates_are_unix(client):
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.startswith("date_"):
                    assert value is None or (isinstance(value, int) and not isinstance(value, bool)), key
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for resource in ("status", "hosts", "updates"):
        walk(client.get("/api/" + resource).json())


def test_api_no_secrets(client):
    for path in ("/api/status", "/api/hosts", "/api/updates", "/health"):
        assert "SENTINEL123" not in client.get(path).text


def test_health_endpoint_serves_evaluation(client):
    body = client.get("/health").json()
    assert body["health"] in ("good", "warning", "error") and len(body["message"]) <= 100
