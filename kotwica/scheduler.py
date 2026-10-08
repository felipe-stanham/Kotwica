"""Two independent periodic jobs (sync, watch) as asyncio tasks."""
import asyncio
import logging
from typing import Awaitable, Callable, List

log = logging.getLogger(__name__)

Job = Callable[[], Awaitable[None]]


class Scheduler:
    def __init__(self, sync_job: Job, watch_job: Job, sync_interval_s: float, watch_interval_s: float):
        self._jobs = [("sync", sync_job, sync_interval_s), ("watch", watch_job, watch_interval_s)]
        self._tasks: List[asyncio.Task] = []

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._run(name, job, interval), name="kotwica-" + name)
            for name, job, interval in self._jobs
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    @staticmethod
    async def _run(name: str, job: Job, interval_s: float) -> None:
        """Run the job now, then every interval. A failing cycle is logged and never stops the loop."""
        while True:
            try:
                await job()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("%s job failed", name)
            await asyncio.sleep(interval_s)
