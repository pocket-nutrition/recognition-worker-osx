"""Calls to the recognition server's `/worker` routes. Outbound only."""

import httpx

from worker.config import Settings
from worker.schemas import CaptureResult, Job


class LeaseLost(Exception):
    """The server no longer holds this job for us (expired, finished, or deleted)."""


class ServerClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._wait = settings.claim_wait_s
        self._http = httpx.AsyncClient(
            base_url=settings.server_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.key}"},
            # Long poll: the read timeout must outlast the server-side wait.
            timeout=httpx.Timeout(30, read=settings.claim_wait_s + 15),
            follow_redirects=False,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _check(resp: httpx.Response) -> httpx.Response:
        if resp.status_code == 409:
            raise LeaseLost(resp.text)
        resp.raise_for_status()
        return resp

    async def claim(self) -> Job | None:
        resp = await self._http.post("/worker/claim", params={"wait": self._wait})
        if resp.status_code == 204:
            return None
        return Job.model_validate(self._check(resp).json())

    async def audio(self, lease_id: str) -> bytes:
        return self._check(await self._http.get(f"/worker/leases/{lease_id}/audio")).content

    async def progress(self, lease_id: str, status: str) -> None:
        self._check(await self._http.post(f"/worker/leases/{lease_id}/progress", json={"status": status}))

    async def complete(self, lease_id: str, delivery: str, result: CaptureResult | None = None) -> None:
        body = {"delivery": delivery, "result": result.model_dump() if result else None}
        self._check(await self._http.post(f"/worker/leases/{lease_id}/complete", json=body))

    async def fail(self, lease_id: str, error: str) -> None:
        self._check(await self._http.post(f"/worker/leases/{lease_id}/fail", json={"error": error[:500]}))
