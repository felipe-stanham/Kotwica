"""Kotwica entry point: Latarnia Service App (CLI args, logging, FastAPI app, lifespan)."""
import argparse
import asyncio
import logging
import os
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
from kotwica.host_watch import make_watch_job
from kotwica.record_sync import make_sync_job
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


def order_jobs(sync_job: Job, watch_job: Job, wait_s: float = 30.0):
    """The first watch cycle waits (briefly) for the first sync, so it already knows the Public IP."""
    first_sync_done = asyncio.Event()
    first_watch = True

    async def sync() -> None:
        try:
            await sync_job()
        finally:
            first_sync_done.set()

    async def watch() -> None:
        nonlocal first_watch
        if first_watch:
            first_watch = False
            try:
                await asyncio.wait_for(first_sync_done.wait(), wait_s)
            except asyncio.TimeoutError:
                log.warning("First sync did not finish in %ss; watching without a Public IP", wait_s)
        await watch_job()

    return sync, watch


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
    sync_job, watch_job = order_jobs(make_sync_job(config, store), make_watch_job(config, store))
    app = create_app(config, store, sync_job, watch_job)
    # uvicorn re-raises a captured SIGTERM after its graceful shutdown; with the default handler
    # that would kill the process with -15 instead of exit code 0.
    signal.signal(signal.SIGTERM, lambda *_: None)
    server = uvicorn.Server(
        uvicorn.Config(app, host=args.host, port=config.port, log_config=None, access_log=False)
    )
    asyncio.new_event_loop().run_until_complete(server.serve())
    # DNS and TLS checks run in executor threads that cannot be cancelled (socket timeouts up to 10 s).
    # asyncio.run and interpreter exit would both join them and delay the exit past the stop timeout,
    # so after the graceful shutdown leave without joining (main therefore never returns 0; only errors return).
    logging.shutdown()
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
