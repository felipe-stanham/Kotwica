"""app.order_jobs: the first watch cycle waits for the first sync."""
import asyncio

import app as app_module


def test_first_watch_waits_for_first_sync():
    events = []

    async def sync_job():
        await asyncio.sleep(0.2)
        events.append("sync")

    async def watch_job():
        events.append("watch")

    async def run():
        sync, watch = app_module.order_jobs(sync_job, watch_job)
        await asyncio.gather(watch(), sync())
        await watch()  # later cycles do not wait

    asyncio.run(run())
    assert events == ["sync", "watch", "watch"]


def test_first_watch_gives_up_waiting_after_timeout():
    events = []

    async def never():
        await asyncio.sleep(10)

    async def watch_job():
        events.append("watch")

    async def run():
        _sync, watch = app_module.order_jobs(never, watch_job, wait_s=0.1)
        await watch()

    asyncio.run(run())
    assert events == ["watch"]


def test_sync_failure_still_releases_the_watch():
    events = []

    async def sync_job():
        raise RuntimeError("boom")

    async def watch_job():
        events.append("watch")

    async def run():
        sync, watch = app_module.order_jobs(sync_job, watch_job)
        try:
            await sync()
        except RuntimeError:
            pass
        await watch()

    asyncio.run(run())
    assert events == ["watch"]
