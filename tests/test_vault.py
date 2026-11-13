import base64

import pytest
from nacl.public import PrivateKey

from worker.config import Settings
from worker.schemas import Drop
from worker.vault import InvalidDrop, check_drop

KEY = base64.b64encode(bytes(PrivateKey.generate().public_key)).decode()
STRICT = Settings(server_url="https://s", key="k" * 20)


def drop(url="https://vault.example", key=KEY) -> Drop:
    return Drop(url=url, token="t", record_id="r", inbox_public_key=key)


@pytest.mark.parametrize(
    "url",
    [
        "http://vault.example",  # not https
        "https://user:pw@vault.example",  # credentials in URL
        "https://127.0.0.1",  # loopback
        "https://192.168.1.10",  # home network
        "https://169.254.169.254",  # link-local metadata
        "https://[::1]",
        "file:///etc/passwd",
    ],
)
async def test_unsafe_vault_urls_are_refused(url):
    with pytest.raises(InvalidDrop):
        await check_drop(drop(url), STRICT)


async def test_malformed_inbox_key_is_refused(settings):
    with pytest.raises(InvalidDrop):
        await check_drop(drop("http://vault.test", key="not-base64!"), settings)
    with pytest.raises(InvalidDrop):
        await check_drop(drop("http://vault.test", key=base64.b64encode(b"short").decode()), settings)


async def test_origin_is_normalised(settings):
    origin, key = await check_drop(drop("http://vault.test/some/path?x=1"), settings)
    assert origin == "http://vault.test" and len(key) == 32


def private_host(monkeypatch, address="192.168.1.105"):
    """Makes every hostname resolve to `address`, like split-horizon DNS on the home network."""
    monkeypatch.setattr(
        "worker.vault.socket.getaddrinfo", lambda host, port: [(2, 1, 6, "", (address, port))]
    )


async def test_a_host_resolving_to_the_lan_is_refused_by_default(monkeypatch):
    private_host(monkeypatch)
    with pytest.raises(InvalidDrop):
        await check_drop(drop("https://vault.example"), STRICT)


async def test_a_trusted_host_may_resolve_to_the_lan(monkeypatch):
    private_host(monkeypatch)
    trusted = Settings(server_url="https://s", key="k" * 20, vault_trusted_hosts="Vault.Example, other.example")
    origin, _ = await check_drop(drop("https://vault.example"), trusted)
    assert origin == "https://vault.example"


async def test_trust_is_per_host_not_a_blanket_exemption(monkeypatch):
    private_host(monkeypatch)
    trusted = Settings(server_url="https://s", key="k" * 20, vault_trusted_hosts="vault.example")
    with pytest.raises(InvalidDrop):
        await check_drop(drop("https://evil.example"), trusted)
    # A sibling or look-alike name is not the trusted one.
    with pytest.raises(InvalidDrop):
        await check_drop(drop("https://vault.example.evil.example"), trusted)


async def test_a_trusted_host_still_needs_https_and_no_credentials(monkeypatch):
    private_host(monkeypatch)
    trusted = Settings(server_url="https://s", key="k" * 20, vault_trusted_hosts="vault.example")
    for url in ("http://vault.example", "https://user:pw@vault.example"):
        with pytest.raises(InvalidDrop):
            await check_drop(drop(url), trusted)


@pytest.mark.parametrize("key", [bytes(32), b"\x01" + bytes(31)])
async def test_a_key_that_cannot_seal_is_refused_up_front(settings, key):
    with pytest.raises(InvalidDrop):
        await check_drop(drop("http://vault.test", key=base64.b64encode(key).decode()), settings)
