import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class AppProcess:
    def __init__(self, data_dir: Path, env: dict = None, port: int = None, env_file: Path = None):
        self.port = port or free_port()
        self.data_dir = data_dir
        full_env = {k: v for k, v in os.environ.items() if k not in ("ENV", "GODADDY_API_TOKEN")}
        full_env.update({"ENV": "dev", "PYTHONUNBUFFERED": "1"})
        full_env.update(env or {})
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "app.py"), "--port", str(self.port), "--data-dir", str(data_dir),
             "--env-file", str(env_file or data_dir.parent / "no.env")],
            cwd=str(ROOT), env=full_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    def wait_ready(self, timeout: float = 5.0):
        import httpx

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                return httpx.get("http://127.0.0.1:%d/health" % self.port, timeout=1)
            except httpx.TransportError:
                time.sleep(0.1)
        raise AssertionError("app did not answer /health within %ss" % timeout)

    def terminate(self, timeout: float = 5.0) -> int:
        self.proc.send_signal(signal.SIGTERM)
        return self.proc.wait(timeout=timeout)

    def output(self) -> str:
        return self.proc.stdout.read()

    def kill(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()


@pytest.fixture
def app_process(tmp_path):
    started = []

    def start(env: dict = None, data_dir: Path = None, env_file: Path = None):
        p = AppProcess(data_dir or tmp_path / "data", env, env_file=env_file)
        started.append(p)
        return p

    yield start
    for p in started:
        p.kill()
