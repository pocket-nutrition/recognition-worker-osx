# Contributing to the Pocket Nutrition Recognition Worker

Thanks for your interest in improving this worker. It is a small, single-purpose agent, so the contribution
process is intentionally lightweight.

## Development setup

```bash
git clone https://github.com/pocket-nutrition/recognition-worker-osx.git
cd recognition-worker-osx
./setup.sh                       # creates .venv (Python 3.12), installs dependencies, copies .env.example → .env
```

Or set up manually:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
```

You do not need Handy, LM Studio or a recognition server to work on most of the code: the tests mock every
call out. The tests run on macOS and on Linux. Running real jobs needs macOS on Apple silicon, ffmpeg, Handy
with the Cohere Transcribe model and LM Studio's local server (see [README.md](README.md)).

To run the worker in the foreground against your own recognition server, set `WORKER_SERVER_URL` and
`WORKER_KEY` in `.env`, then:

```bash
.venv/bin/python -m worker.main
```

## Running tests

```bash
.venv/bin/pytest
```

Two tests call the real `ffmpeg` and `ffprobe`. They are skipped when ffmpeg is not installed (`pytest -rs`
lists skips), so install it to run them: `brew install ffmpeg` on macOS.

`Settings` reads `.env` from the working directory, including in tests, so a customised `.env` can change the
results: `WORKER_VISION_LANGUAGE=en` or a `WORKER_VAULT_TRUSTED_HOSTS` entry each make a test fail. If a test
fails only on your machine, move `.env` aside and run it again.

There is no linter, formatter or coverage gate in this repository. Keep changes consistent with the
surrounding style: type hints on function signatures, short docstrings that say why, and English identifiers,
comments and messages.

## Test-first expectations

This worker sits between untrusted input and a user's vault, so small changes can have large effects. For any
change to `worker/pipeline.py`, `worker/vault.py`, `worker/stt.py`, `worker/vision.py`, `worker/extract.py`,
`worker/resolve.py` or `worker/client.py`:

1. Add or update a test in `tests/` that captures the behavior you're adding or fixing.
2. Confirm the test fails without your change and passes with it.
3. Run the full suite (`.venv/bin/pytest`) before opening a pull request. It must pass.

Tests mock every call out. Functions that call out take an optional `transport`, which tests set to an
`httpx.MockTransport`, and the slow stages are injected through `Steps` (see `make_steps` in
`tests/test_pipeline.py`). `pytest.ini` sets `asyncio_mode = auto`, so write `async def test_...` with no
decorator.

Pull requests that change behavior without an accompanying test will be asked to add one.

## Security invariants

Read the "Invariants" section in [CLAUDE.md](CLAUDE.md) before touching the pipeline. The worker runs on a
machine on a private network and handles content anyone with the app can send, so audio, photos, transcripts
and the vault address are all untrusted. A change must not:

- make the worker accept incoming connections: it only makes outgoing calls;
- keep audio or photos, or write a transcript, a photo, a vault URL or token, or the key to a log line;
- loosen the vault checks in `worker/vault.py` (https only, public addresses only, no redirects), or let a
  phone add to `WORKER_VAULT_TRUSTED_HOSTS`;
- send the server anything but an error type, or "no speech detected", as a failure reason;
- let a model supply ingredient candidates, or use a model's answer without validating it.

If you think one of these has to change, open an issue first.

## Branch and PR workflow

1. Fork the repository and create a feature branch off `main`.
2. Make focused commits with clear messages (e.g. `docs: explain the Handy model setting`).
3. Ensure `.venv/bin/pytest` passes locally.
4. Open a pull request describing the change and, for behavioral changes, what test covers it.
5. Be responsive to review feedback. Small, focused PRs are easier to review and merge.

## Reporting issues

Please open a GitHub issue describing the problem. Include your macOS version and chip, how you run the worker
(launchd agent or foreground), the versions of Handy and LM Studio and the models you use, whether the job was
a recording or a photo, and the error type the app showed.

Log lines help, but redact them first: never post your `WORKER_KEY`, a vault URL or token, or a transcript or
photo, and remember that error details in the log can contain fragments of what was said.

Security problems (for example a way to make the worker call into a private network, or to expose audio,
photos or transcripts) do not belong in a public issue. Use "Report a vulnerability" on the repository's
Security tab instead.

## CI

- Every pull request runs `.github/workflows/ci.yml`: the tests on Linux with Python 3.12 and ffmpeg
  installed. The `ci-success` check must be green before a pull request can be merged, the branch must be up to
  date with `main`, and pull requests are squash-merged so history stays linear.
- If you contribute from a fork, the workflow waits for a maintainer to approve it. It runs with a read-only
  token and no secrets.
- There is no release pipeline and no container image: the worker runs from a checkout
  (`deploy/launchd.sh`).

## Using Claude Code

This repository includes a [CLAUDE.md](CLAUDE.md) with the processing flow, the layout, the commands and the
invariants. Run `claude` in the repository root and it reads the file automatically.
