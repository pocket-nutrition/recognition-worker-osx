from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORKER_", env_file=".env", extra="ignore")

    server_url: str
    key: str
    handy_bin: str = "/Applications/Handy.app/Contents/MacOS/handy"
    handy_model: str = "handy-computer/cohere-transcribe-03-2026-gguf/cohere-transcribe-03-2026-Q5_K_M.gguf"
    ffmpeg_bin: str = "ffmpeg"
    llm_url: str = "http://127.0.0.1:1234/v1"
    llm_model: str = "gemma-4-12b-it-qat"
    # Model used for photos; must accept image input. Empty: llm_model is used.
    vision_model: str = ""
    # Photos carry no language: queries are written in this one ("fr" or "en").
    vision_language: Literal["fr", "en"] = "fr"
    max_image_px: int = 1024
    api_url: str = "https://api.pocketnutrition.org"
    max_audio_secs: int = 120
    stt_timeout_s: float = 120
    llm_timeout_s: float = 120
    # Must stay <= the server's max_wait_s (25).
    claim_wait_s: float = 20
    heartbeat_s: float = 30
    candidates_per_item: int = 5
    max_items: int = 20
    vault_timeout_s: float = 10
    vault_retry_delays_s: tuple[float, ...] = (1, 5, 30)
    # Comma-separated vault hostnames that may resolve to a private address (split-horizon DNS: on a private
    # network, a vault domain you run may point at a local address). Set by whoever runs this machine only: a
    # phone cannot add to it. Every other vault host must still resolve to public addresses.
    vault_trusted_hosts: str = ""
    # Tests only: allow http and non-public hosts for the vault.
    vault_allow_insecure: bool = False

    @property
    def photo_model(self) -> str:
        return self.vision_model or self.llm_model

    @property
    def trusted_vault_hosts(self) -> frozenset[str]:
        return frozenset(h.strip().lower() for h in self.vault_trusted_hosts.split(",") if h.strip())
