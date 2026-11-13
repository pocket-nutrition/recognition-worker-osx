"""Seal a result to the phone's inbox key and deposit it in the vault with a write-only drop token.

The drop target comes from the phone, so it is untrusted: this worker typically runs on a private (home or
office) network, and an unchecked `vault_url` would let a stranger make it call into that network. https +
public addresses only, no redirects. The one exception is `vault_trusted_hosts`, a list only the operator of
this machine can set, for a vault whose domain resolves to a private address from inside that network.
Mirrors `app/vault.py` in https://github.com/pocket-nutrition/recognition.
"""

import asyncio
import base64
import binascii
import ipaddress
import json
import logging
import socket
from urllib.parse import urlsplit

import httpx
from nacl.exceptions import CryptoError
from nacl.public import PublicKey, SealedBox

from worker.config import Settings
from worker.schemas import Drop

log = logging.getLogger(__name__)

PAYLOAD_VERSION = 1


class InvalidDrop(ValueError):
    pass


async def check_drop(drop: Drop, settings: Settings) -> tuple[str, bytes]:
    """Return the normalised vault origin and the decoded inbox key, or raise InvalidDrop."""
    parts = urlsplit(drop.url)
    if parts.scheme != "https" and not settings.vault_allow_insecure:
        raise InvalidDrop("vault url must be https")
    if not parts.hostname or parts.username or parts.password:
        raise InvalidDrop("vault url must be a plain host URL")
    trusted = parts.hostname.lower() in settings.trusted_vault_hosts
    if not settings.vault_allow_insecure and not trusted:
        try:
            infos = await asyncio.to_thread(socket.getaddrinfo, parts.hostname, parts.port or 443)
        except socket.gaierror as exc:
            raise InvalidDrop("vault host does not resolve") from exc
        if not all(ipaddress.ip_address(info[4][0]).is_global for info in infos):
            raise InvalidDrop("vault url must point to a public address")
    try:
        key = base64.b64decode(drop.inbox_public_key, validate=True)
        # Right length is not enough (all zeros, low-order points): sealing would crash later, in the middle
        # of a job. Try it now so the drop is refused up front.
        SealedBox(PublicKey(key)).encrypt(b"x")
    except (binascii.Error, ValueError, TypeError, CryptoError) as exc:
        raise InvalidDrop("inbox key must be a base64 X25519 public key") from exc
    return f"{parts.scheme}://{parts.netloc}", key


def seal(payload: dict, inbox_public_key: bytes) -> str:
    plaintext = json.dumps(payload, separators=(",", ":")).encode()
    return base64.b64encode(SealedBox(PublicKey(inbox_public_key)).encrypt(plaintext)).decode()


async def deposit(
    drop: Drop,
    payload: dict,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """Seal and deposit. Returns False when the vault did not take it (invalid target included)."""
    try:
        origin, key = await check_drop(drop, settings)
    except InvalidDrop as exc:
        log.warning("refusing vault drop: %s", exc)
        return False
    body = {"ciphertext": seal(payload, key)}
    headers = {"Authorization": f"Bearer {drop.token}"}
    delays = settings.vault_retry_delays_s
    async with httpx.AsyncClient(
        transport=transport, timeout=settings.vault_timeout_s, follow_redirects=False
    ) as client:
        for attempt in range(len(delays) + 1):
            try:
                resp = await client.put(f"{origin}/v1/drop", json=body, headers=headers)
            except httpx.HTTPError as exc:
                log.warning("vault deposit attempt %d failed: %s", attempt + 1, type(exc).__name__)
            else:
                if resp.status_code == 200:
                    return True
                if resp.status_code < 500:
                    # Expired, exhausted or revoked token: retrying cannot help.
                    log.warning("vault rejected the drop with %d", resp.status_code)
                    return False
            if attempt < len(delays):
                await asyncio.sleep(delays[attempt])
    return False
