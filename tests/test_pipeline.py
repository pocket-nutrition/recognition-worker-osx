import base64
import json

import httpx
import pytest
from nacl.public import PrivateKey, SealedBox

from worker.client import LeaseLost, ServerClient
from worker.pipeline import Steps, process
from worker.schemas import Drop, Extraction, ExtractedItem, Job, SpokenItem, Candidate


class FakeServer:
    """Records the worker's calls to /worker/leases/*."""

    def __init__(self, lease_lost: bool = False):
        self.calls: list[tuple[str, dict | None]] = []
        self.lease_lost = lease_lost

    def __call__(self, request: httpx.Request) -> httpx.Response:
        action = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content) if request.content else None
        self.calls.append((action, body))
        if self.lease_lost:
            return httpx.Response(409, json={"detail": "gone"})
        if action == "audio":
            return httpx.Response(200, content=b"audio-bytes")
        return httpx.Response(204)

    def sent(self, action: str) -> list[dict | None]:
        return [body for name, body in self.calls if name == action]


class FakeVault:
    def __init__(self, status: int = 200):
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json={})


def make_steps(transcript="une pomme", fail_at=None) -> Steps:
    steps = Steps.__new__(Steps)

    async def stt(audio: bytes) -> str:
        assert audio == b"audio-bytes"
        if fail_at == "stt":
            raise RuntimeError("boom with secret words")
        return transcript

    async def llm(text: str) -> Extraction:
        return Extraction(language="fr", items=[SpokenItem(raw_text=text, query="pomme", quantity=1, unit="piece")])

    async def search(extraction: Extraction):
        return [
            ExtractedItem(
                raw_text=i.raw_text,
                quantity=i.quantity,
                unit=i.unit,
                candidates=[Candidate(ingredient_id="pomme_crue", name="Apple, raw", score=0.95)],
            )
            for i in extraction.items
        ]

    steps.transcribe, steps.extract, steps.resolve = stt, llm, search
    return steps


def make_job(inbox: PrivateKey | None = None) -> Job:
    drop = None
    if inbox:
        drop = Drop(
            url="http://vault.test",
            token="pnv_drop",
            record_id="capture-1",
            inbox_public_key=base64.b64encode(bytes(inbox.public_key)).decode(),
        )
    return Job(lease_id="L1", ticket_id="T1", lease_expires_at=0, audio_content_type="audio/mp4", drop=drop)


def open_payload(vault: FakeVault, inbox: PrivateKey) -> dict:
    (request,) = vault.requests
    sealed = base64.b64decode(json.loads(request.content)["ciphertext"])
    return json.loads(SealedBox(inbox).decrypt(sealed))


async def run(job, settings, steps, server, vault=None):
    client = ServerClient(settings, transport=httpx.MockTransport(server))
    try:
        await process(job, client, settings, steps, vault_transport=httpx.MockTransport(vault) if vault else None)
    finally:
        await client.aclose()


async def test_without_a_vault_the_result_goes_back_to_the_server(settings):
    server = FakeServer()
    await run(make_job(), settings, make_steps(), server)

    assert [name for name, _ in server.calls] == ["audio", "progress", "progress", "complete"]
    assert [b["status"] for b in server.sent("progress")] == ["transcribing", "extracting"]
    (done,) = server.sent("complete")
    assert done["delivery"] == "none" and done["result"]["items"][0]["candidates"][0]["ingredient_id"] == "pomme_crue"


async def test_with_a_vault_the_result_is_sealed_there_and_never_sent_to_the_server(settings):
    inbox, server, vault = PrivateKey.generate(), FakeServer(), FakeVault()
    await run(make_job(inbox), settings, make_steps(), server, vault)

    (done,) = server.sent("complete")
    assert done == {"delivery": "delivered", "result": None}

    payload = open_payload(vault, inbox)
    assert payload["record_id"] == "capture-1" and payload["ticket_id"] == "T1" and payload["status"] == "done"
    assert payload["result"]["transcript"] == "une pomme"
    assert vault.requests[0].headers["authorization"] == "Bearer pnv_drop"
    assert str(vault.requests[0].url) == "http://vault.test/v1/drop"


async def test_a_refused_deposit_falls_back_to_the_ticket(settings):
    inbox, server, vault = PrivateKey.generate(), FakeServer(), FakeVault(status=401)
    await run(make_job(inbox), settings, make_steps(), server, vault)

    (done,) = server.sent("complete")
    assert done["delivery"] == "failed" and done["result"]["transcript"] == "une pomme"


async def test_silence_fails_the_job_with_a_readable_reason(settings):
    inbox, server, vault = PrivateKey.generate(), FakeServer(), FakeVault()
    await run(make_job(inbox), settings, make_steps(transcript="  "), server, vault)

    (failed,) = server.sent("fail")
    assert failed == {"error": "no speech detected"}
    payload = open_payload(vault, inbox)
    assert payload["status"] == "failed" and payload["error"] == "no speech detected"


async def test_unexpected_errors_report_only_the_error_type(settings):
    server = FakeServer()
    await run(make_job(), settings, make_steps(fail_at="stt"), server)
    (failed,) = server.sent("fail")
    assert failed == {"error": "RuntimeError"}  # the message may contain what the user said


async def test_a_lost_lease_ends_quietly(settings):
    server = FakeServer(lease_lost=True)
    await run(make_job(), settings, make_steps(), server)  # must not raise
    assert [name for name, _ in server.calls] == ["audio"]


async def test_client_maps_409_to_lease_lost(settings):
    client = ServerClient(settings, transport=httpx.MockTransport(FakeServer(lease_lost=True)))
    with pytest.raises(LeaseLost):
        await client.progress("L1", "extracting")
    await client.aclose()


def make_photo_steps(items=1) -> Steps:
    steps = make_steps()

    async def see(image: bytes):
        assert image == b"audio-bytes"  # FakeServer serves the same bytes for any media
        seen = [SpokenItem(raw_text="pomme rouge", query="pomme", quantity=150, unit="g")] * items
        return "Une pomme rouge sur une assiette.", Extraction(language="fr", items=seen)

    async def no_stt(audio: bytes) -> str:
        raise AssertionError("a photo must not be transcribed")

    steps.see, steps.transcribe = see, no_stt
    return steps


def make_photo_job(inbox: PrivateKey | None = None) -> Job:
    return make_job(inbox).model_copy(update={"audio_content_type": "image/jpeg"})


async def test_a_photo_skips_transcription_and_reports_only_extracting(settings):
    server = FakeServer()
    await run(make_photo_job(), settings, make_photo_steps(), server)

    assert [name for name, _ in server.calls] == ["audio", "progress", "complete"]
    assert [b["status"] for b in server.sent("progress")] == ["extracting"]
    (done,) = server.sent("complete")
    assert done["result"]["transcript"] == "Une pomme rouge sur une assiette."
    assert done["result"]["items"][0]["quantity"] == 150


async def test_a_photo_result_is_sealed_into_the_vault(settings):
    inbox, server, vault = PrivateKey.generate(), FakeServer(), FakeVault()
    await run(make_photo_job(inbox), settings, make_photo_steps(), server, vault)

    assert server.sent("complete") == [{"delivery": "delivered", "result": None}]
    assert open_payload(vault, inbox)["result"]["items"][0]["candidates"][0]["ingredient_id"] == "pomme_crue"


async def test_a_photo_without_food_completes_with_no_items(settings):
    server = FakeServer()
    await run(make_photo_job(), settings, make_photo_steps(items=0), server)
    (done,) = server.sent("complete")
    assert done["result"]["items"] == [] and not server.sent("fail")
