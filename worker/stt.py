"""Speech-to-text through Handy's headless mode (`handy --transcribe-file`), Cohere Transcribe model."""

import asyncio
import json
import tempfile
from pathlib import Path

from worker.config import Settings


class TranscriptionError(Exception):
    pass


async def _run(argv: list[str], timeout: float) -> tuple[int, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TranscriptionError(f"{Path(argv[0]).name} timed out")
    return proc.returncode, out


def parse_handy_output(stdout: bytes) -> str:
    """Handy logs to stdout too; the result is the last line that is a JSON object."""
    for line in reversed(stdout.decode(errors="replace").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return str(json.loads(line)["text"]).strip()
            except (ValueError, KeyError) as exc:
                raise TranscriptionError("unreadable Handy output") from exc
    raise TranscriptionError("Handy produced no result")


async def transcribe(audio: bytes, settings: Settings) -> str:
    """Convert the clip to 16 kHz mono WAV and transcribe it. Audio never leaves a private temp dir."""
    with tempfile.TemporaryDirectory(prefix="pn-worker-") as tmp:
        src, wav = Path(tmp) / "in.bin", Path(tmp) / "clip.wav"
        src.write_bytes(audio)
        code, _ = await _run(
            [
                settings.ffmpeg_bin, "-nostdin", "-loglevel", "error", "-y",
                # The clip is untrusted input: keep ffmpeg to local files only.
                "-protocol_whitelist", "file",
                "-t", str(settings.max_audio_secs),
                "-i", str(src), "-vn", "-ar", "16000", "-ac", "1", str(wav),
            ],
            timeout=60,
        )
        if code != 0 or not wav.exists():
            raise TranscriptionError("audio could not be decoded")
        code, out = await _run(
            [settings.handy_bin, "-f", str(wav), "--model", settings.handy_model, "--json"],
            timeout=settings.stt_timeout_s,
        )
        if code != 0:
            raise TranscriptionError(f"Handy exited with {code}")
        return parse_handy_output(out)
