# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Worker that runs on a Mac you control and processes meal-recording and meal-photo jobs for [`recognition`](https://github.com/pocket-nutrition/recognition) (worker pipeline). It **pulls** work, so nothing on the Mac is exposed to the internet.

**Stack:** Python 3.12, httpx, PyNaCl (sealed boxes), pydantic and pydantic-settings, pytest with pytest-asyncio. No web framework: the worker serves nothing.

```
claim (long poll) → audio → ffmpeg → Handy (Cohere Transcribe) → LLM (LM Studio, Gemma) → ingredient search
   → seal to the phone's inbox key → PUT {vault}/v1/drop → complete(delivered)
claim → photo (image/*) → ffmpeg re-encode (JPEG, ≤ max_image_px, no metadata) → vision LLM → ingredient search → …
```

A job is a photo when its `audio_content_type` starts with `image/` (the server's media route keeps the name `audio`). Photos skip the `transcribing` stage, and the model's one-line description is returned in `transcript` so the phone needs no new field. `WORKER_VISION_MODEL` must accept images; empty means `WORKER_LLM_MODEL` is used (`google/gemma-4-e4b` does, ~30 s per photo on an Apple silicon MacBook, 2026-11-02).

Contract with the server: [`recognition`](https://github.com/pocket-nutrition/recognition), `CLAUDE.md` ("Worker routes"). Wire shapes: `worker/schemas.py`.

## Layout

```
worker/
  main.py      # claim loop: one job at a time, backoff when a claim fails, stops on SIGINT/SIGTERM between jobs
  pipeline.py  # process(): one job from claim to completion; Steps (injectable slow stages); heartbeat
  client.py    # ServerClient: the server's /worker routes (claim, audio, progress, complete, fail)
  stt.py       # ffmpeg to 16 kHz mono WAV, then Handy headless (Cohere Transcribe)
  vision.py    # photo: ffmpeg re-encode to a bounded JPEG, then the vision model
  extract.py   # transcript to structured items with the local LLM; chat_json() validates every answer
  resolve.py   # item names to ranked candidates from the public ingredient search
  vault.py     # checks the drop target, seals to the inbox key, PUT {vault}/v1/drop with retries
  schemas.py   # wire shapes (Job, Drop, CaptureResult) and what a model may say (Extraction, SeenMeal)
  config.py    # Settings: WORKER_* variables, read from the environment and from .env
deploy/        # launchd.sh (install | uninstall | status | logs) and the launchd plist template
tests/         # pytest: test_pipeline, test_steps, test_vault, test_vision
```

## Invariants

- Own credential `WORKER_KEY`, never the phone key. Outbound calls only.
- Results are sealed into the vault by this worker; on `delivered` nothing is sent to the server. Only when the deposit fails (or no vault was requested) is the result sent to the server as fallback.
- The drop target (`vault_url`) comes from a phone, so it is untrusted and this machine typically sits on a private (home or office) network: https + public addresses only, no redirects (`worker/vault.py`). Never loosen outside tests.
- The audio is untrusted input: ffmpeg runs with `-protocol_whitelist file`, a duration cap, and a private temp dir that is deleted afterwards. Audio is never kept.
- The photo is untrusted input too: it is re-encoded by ffmpeg (same sandboxing as audio) before the model server ever sees it, and the model is told to ignore text written in the image.
- The transcript is untrusted text: the LLM is told so, its output is validated against `Extraction` (enums, bounded numbers, capped item count), and candidates come only from the ingredient search, never from the model.
- Failure reasons sent to the server are the error type only, or "no speech detected": exception messages may contain what the user said. A photo with no food completes with an empty item list (not a failure).
- One job at a time; a heartbeat (`progress`) keeps the lease alive during slow stages.

## Dev

```bash
./setup.sh                        # .venv (Python 3.12), dependencies, .env from .env.example
.venv/bin/pytest                  # tests
.venv/bin/python -m worker.main   # run in the foreground; Ctrl-C stops it once the current poll or job ends
```

Edit `.env` first: `WORKER_SERVER_URL` and `WORKER_KEY` have no usable default. By hand instead of the script: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`, then `cp .env.example .env`. No linter, formatter or coverage gate is configured.

To run real jobs (the tests need none of this except ffmpeg, for two tests): Handy installed with the Cohere model downloaded, `ffmpeg` on PATH, and LM Studio's local server running with the model in `WORKER_LLM_MODEL` loaded (`lms server start` could not start the daemon headless on 2026-10-25: open the LM Studio app first).

## Tests

- `pytest.ini` sets `asyncio_mode = auto`: write `async def test_...` with no decorator.
- Every call out is mocked. Functions that call out take an optional `transport` (`httpx.MockTransport`), and the slow stages are injected through `Steps` (see `make_steps` in `tests/test_pipeline.py`).
- Two tests in `tests/test_vision.py` run the real `ffmpeg` and `ffprobe`. They are skipped when ffmpeg is missing: use `pytest -rs` to see skips.
- `Settings` reads `.env` from the working directory, so a customised `.env` can change test results (`WORKER_VISION_LANGUAGE=en` or a `WORKER_VAULT_TRUSTED_HOSTS` entry each fail a test). If a test fails only on your machine, move `.env` aside and run it again.

## Running at login (launchd)

`deploy/launchd.sh install` installs a per-user agent (starts at login, restarts after a crash, 30 s throttle). It refuses to install without `.env` and a `WORKER_KEY` of 16+ characters, and sets `.env` to `chmod 600`: the key is never written into the plist. `status`, `logs` and `uninstall` do what they say; logs go to `~/Library/Logs/recognition-worker.log`. The agent does not start LM Studio: the model server must be up, otherwise jobs fail at extraction.

## Conventions

- All code, comments, docs and commit messages in English.
- `worker/schemas.py` and `worker/vault.py` mirror the recognition server (`app/schemas.py`, `app/worker.py`, `app/vault.py`): change both sides together.
- A user-facing setting is a `WORKER_*` field in `worker/config.py` and a commented line in `.env.example`. `vault_allow_insecure` is the exception: it switches the vault checks off, tests set it in `tests/conftest.py`, and it stays out of `.env.example` and the user documentation.
- Log ticket ids, error types and fixed messages. Never log a transcript, a photo, a vault URL or token, or the key. The tracebacks that `process()` and its heartbeat log (`worker/pipeline.py`) are the one place details land, and they stay on the Mac.
- Type hints on signatures; short docstrings that say why. Match the surrounding style.
