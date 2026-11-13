"""One job from claim to completion: audio -> transcript (or photo -> description) -> items -> candidates
-> sealed deposit."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from worker import vault
from worker.client import LeaseLost, ServerClient
from worker.config import Settings
from worker.extract import extract
from worker.resolve import resolve
from worker.schemas import CaptureResult, Extraction, Job
from worker.stt import transcribe
from worker.vision import describe, normalize

log = logging.getLogger(__name__)


class NoSpeech(Exception):
    pass


class Steps:
    """The slow stages, injectable so the orchestration can be tested without Handy or an LLM."""

    def __init__(self, settings: Settings):
        self.transcribe: Callable[[bytes], Awaitable[str]] = lambda audio: transcribe(audio, settings)
        self.extract = lambda text: extract(text, settings)
        self.resolve = lambda extraction: resolve(extraction, settings)

        async def see(image: bytes):
            return await describe(await normalize(image, settings), settings)

        self.see: Callable[[bytes], Awaitable[tuple[str, Extraction]]] = see


@asynccontextmanager
async def heartbeat(client: ServerClient, lease_id: str, stage: dict, every_s: float):
    """Keep the lease alive while a slow stage runs."""

    async def beat():
        while True:
            await asyncio.sleep(every_s)
            try:
                await client.progress(lease_id, stage["name"])
            except LeaseLost:
                return
            except Exception:  # transient network error: the next beat retries
                log.warning("heartbeat failed", exc_info=True)

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        task.cancel()


def _payload(job: Job, status: str, result: CaptureResult | None, error: str | None) -> dict:
    return {
        "v": vault.PAYLOAD_VERSION,
        "record_id": job.drop.record_id,
        "ticket_id": job.ticket_id,
        "status": status,
        "result": result.model_dump() if result else None,
        "error": error,
        "completed_at": time.time(),
    }


def is_photo(job: Job) -> bool:
    return job.audio_content_type.lower().startswith("image/")


async def _run_steps(job: Job, client: ServerClient, steps: Steps, stage: dict) -> CaptureResult:
    if is_photo(job):
        return await _run_photo_steps(job, client, steps, stage)
    audio = await client.audio(job.lease_id)
    stage["name"] = "transcribing"
    await client.progress(job.lease_id, "transcribing")
    transcript = await steps.transcribe(audio)
    if not transcript.strip():
        raise NoSpeech("no speech detected")
    stage["name"] = "extracting"
    await client.progress(job.lease_id, "extracting")
    extraction = await steps.extract(transcript)
    items = await steps.resolve(extraction)
    return CaptureResult(transcript=transcript, language=extraction.language, items=items)


async def _run_photo_steps(job: Job, client: ServerClient, steps: Steps, stage: dict) -> CaptureResult:
    # The server's media route is still named "audio"; it serves whatever the phone uploaded.
    image = await client.audio(job.lease_id)
    # No speech stage for a photo: the server only knows transcribing/extracting.
    stage["name"] = "extracting"
    await client.progress(job.lease_id, "extracting")
    description, extraction = await steps.see(image)
    items = await steps.resolve(extraction)
    # The description travels in `transcript` so the phone needs no new field.
    return CaptureResult(transcript=description, language=extraction.language, items=items)


async def process(job: Job, client: ServerClient, settings: Settings, steps: Steps | None = None, vault_transport=None) -> None:
    steps = steps or Steps(settings)
    stage = {"name": "transcribing"}
    deposit = lambda payload: vault.deposit(job.drop, payload, settings, vault_transport)  # noqa: E731
    try:
        async with heartbeat(client, job.lease_id, stage, settings.heartbeat_s):
            result = await _run_steps(job, client, steps, stage)
            if job.drop is None:
                await client.complete(job.lease_id, "none", result)
            elif await deposit(_payload(job, "done", result, None)):
                await client.complete(job.lease_id, "delivered")
            else:
                # Fallback: the phone can still fetch the result from the ticket.
                await client.complete(job.lease_id, "failed", result)
    except LeaseLost:
        log.warning("lost the lease on %s", job.ticket_id)
    except Exception as exc:
        # The detail stays in the log; what the phone sees is a short, content-free reason.
        log.exception("job %s failed", job.ticket_id)
        reason = str(exc) if isinstance(exc, NoSpeech) else type(exc).__name__
        try:
            if job.drop is not None:
                await deposit(_payload(job, "failed", None, reason))
            await client.fail(job.lease_id, reason)
        except LeaseLost:
            pass
