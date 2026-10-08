"""Kotwica entry point: Latarnia Service App (CLI args, logging, FastAPI app, lifespan)."""
import argparse
import logging
import signal
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from kotwica import config as config_module
from kotwica import health, ui_api
from kotwica.config import Config, ConfigError
from kotwica.scheduler import Job, Scheduler
from kotwica.state import StateStore

log = logging.getLogger("kotwica")

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
APP_ROOT = Path(__file__).resolve().parent


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level, format=LOG_FORMAT, datefmt=LOG_DATEFMT, stream=sys.stdout, force=True
    )


def stamp_job(store: StateStore, field_name: str) -> Job:
    """Placeholder job: records that a cycle finished. Replaced by the real jobs in later scopes."""

    async def job() -> None:
        setattr(store.state, field_name, int(time.time()))
        store.save()

    return job


def create_app(config: Config, store: StateStore, sync_job: Job, watch_job: Job) -> FastAPI:
    scheduler = Scheduler(sync_job, watch_job, config.sync_interval_s, config.watch_interval_s)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()

    app = FastAPI(title="Kotwica", lifespan=lifespan)

    @app.get("/health")
    async def health_check():
        return health.evaluate(store.state, config, time.time())

    app.include_router(ui_api.build_router(config, store))

    return app


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kotwica: home DDNS + certificate watch")
    parser.add_argument("--port", type=int, default=8150)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--env-file", type=Path, default=APP_ROOT / ".env")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging()
    try:
        config = config_module.load(
            dotenv_path=args.env_file, port=args.port, data_dir=args.data_dir
        )
    except ConfigError as exc:
        log.error("Invalid configuration: %s", exc)
        return 1
    setup_logging(config.log_level)

    config.data_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config.data_dir / "state.json")
    store.load()
    store.state.reconcile_hosts(config.watched_hosts)

    log.log(
        logging.WARNING if config.env != "dev" else logging.INFO,
        "Kotwica starting: env=%s port=%d managed_record=%s",
        config.env, config.port, config.managed_record,
    )
    app = create_app(config, store, stamp_job(store, "last_sync_at"), stamp_job(store, "last_watch_at"))
    # uvicorn re-raises a captured SIGTERM after its graceful shutdown; with the default handler
    # that would kill the process with -15 instead of exit code 0.
    signal.signal(signal.SIGTERM, lambda *_: None)
    uvicorn.run(app, host=args.host, port=config.port, log_config=None, access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
