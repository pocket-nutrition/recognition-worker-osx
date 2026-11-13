import pytest

from worker.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        server_url="http://server.test",
        key="worker-key-0123456789",
        heartbeat_s=60,
        vault_allow_insecure=True,
        vault_retry_delays_s=(0.01,),
    )
