import asyncio
import logging
import signal

from worker.client import ServerClient
from worker.config import Settings
from worker.pipeline import Steps, process

log = logging.getLogger("worker")

MAX_BACKOFF_S = 60


async def run(settings: Settings, client: ServerClient, stop: asyncio.Event) -> None:
    """Pull and process jobs one at a time until `stop` is set."""
    steps = Steps(settings)
    backoff = 1.0
    while not stop.is_set():
        try:
            job = await client.claim()
            backoff = 1.0
        except Exception as exc:
            log.warning("claim failed (%s), retrying in %.0fs", type(exc).__name__, backoff)
            try:
                await asyncio.wait_for(stop.wait(), backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, MAX_BACKOFF_S)
            continue
        if job is not None:
            log.info("processing ticket %s", job.ticket_id)
            await process(job, client, settings, steps)


async def amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    client = ServerClient(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await run(settings, client, stop)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(amain())
