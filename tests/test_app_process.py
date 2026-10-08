"""cap-001 and the process-level criteria of cap-002 / cap-003 (real subprocess)."""
import json
import re
import time
from pathlib import Path

import app as app_module
from tests.conftest import ROOT


def test_manifest_valid():
    manifest = json.loads((ROOT / "latarnia.json").read_text())
    assert manifest["type"] == "service"
    assert manifest["main_file"] == "app.py"
    assert manifest["config"]["data_dir"] is True
    assert manifest["config"]["has_UI"] is True
    assert manifest["config"]["requires_secrets"] == ["GODADDY_API_TOKEN"]
    assert "port" not in manifest and "port" not in manifest["config"]
    for key in ("name", "version", "description", "author"):
        assert manifest[key]


def test_starts_with_cli_args_and_clean_sigterm(app_process, tmp_path):
    p = app_process()
    response = p.wait_ready(5)
    body = response.json()
    assert response.status_code == 200
    assert body["health"] in ("good", "warning", "error")
    assert isinstance(body["message"], str) and len(body["message"]) <= 100
    assert p.terminate(5) == 0  # sigterm_clean_exit


def test_logs_to_stdout_and_no_log_file(app_process, tmp_path):
    p = app_process()
    p.wait_ready(5)
    p.terminate(5)
    assert re.search(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[INFO\] \S+: ", p.output(), re.M)
    assert [f.name for f in p.data_dir.iterdir() if f.suffix == ".log"] == []


def test_no_reserved_routes():
    from kotwica.config import load

    cfg = load(environ={"ENV": "dev"})
    app = app_module.create_app(cfg, None, None, None)
    # openapi lists every app-defined route; FastAPI's own /docs and /openapi.json are not in it
    defined = list(app.openapi()["paths"])
    assert "/health" in defined
    assert not [p for p in defined if p.startswith("/b/") or p.startswith("/docs") or p == "/openapi.json"]
    assert not [r.path for r in app.routes if getattr(r, "path", "").startswith("/b/")]


def test_guard_home_outside_prod_exits_nonzero(app_process, tmp_path):
    env_file = tmp_path / "guard.env"
    env_file.write_text("DEV_MANAGED_RECORD=home\n")
    p = app_process(env_file=env_file)
    assert p.proc.wait(timeout=5) != 0
    out = p.output()
    assert "[ERROR]" in out and "single-writer guard" in out


def test_first_run_immediate(app_process):
    p = app_process()
    p.wait_ready(5)
    state_file = p.data_dir / "state.json"
    deadline = time.time() + 15
    state = {}
    while time.time() < deadline:
        if state_file.exists():
            state = json.loads(state_file.read_text())
            if state.get("last_sync_at") and state.get("last_watch_at"):
                break
        time.sleep(0.2)
    assert state.get("last_sync_at") and state.get("last_watch_at")


def test_corrupt_state_recovers(app_process, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "state.json").write_text("{not json")
    p = app_process(data_dir=data_dir)
    assert p.wait_ready(5).status_code == 200
    p.terminate(5)
    out = p.output()
    assert re.search(r"\[WARNING\].*state\.json", out)


def test_token_never_logged_at_debug(app_process):
    # The record-sync path with a token is covered in-process (test_record_sync); here the real process runs
    # its sync cycle without a Managed Record so no request ever reaches the real GoDaddy API.
    p = app_process(env={"GODADDY_API_TOKEN": "gd_pat_SENTINEL123", "DEV_MANAGED_RECORD": "none"})
    p.wait_ready(5)
    time.sleep(1)  # let the first cycles run
    p.terminate(5)
    assert "SENTINEL123" not in p.output()
