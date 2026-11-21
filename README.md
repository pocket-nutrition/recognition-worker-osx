# Pocket Nutrition — Recognition Worker (macOS)

Processes [Pocket Nutrition](https://github.com/pocket-nutrition) meal recordings and photos with local
models on a Mac. It pulls jobs, so nothing on the Mac is exposed.

## Where it fits

The Pocket Nutrition apps ([iOS](https://github.com/pocket-nutrition/ios),
[Android](https://github.com/pocket-nutrition/android)) can send a voice recording or a photo of a meal to a
[recognition server](https://github.com/pocket-nutrition/recognition). In worker mode the server only queues
them. This worker does the processing: it runs on a Mac you control, claims jobs from the server by long poll,
and turns each one into a list of foods with ranked ingredient candidates. Without a worker, jobs wait in the
server's queue until they expire.

```
claim a job (long poll)
  recording → ffmpeg → Handy (Cohere Transcribe) → local LLM (LM Studio) → ingredient search
  photo     → ffmpeg re-encode → local vision model (LM Studio)          → ingredient search
seal the result to the phone's inbox key → deposit it in the user's vault
```

- Speech is transcribed locally with [Handy](https://handy.computer) and its Cohere Transcribe model.
- A local model served by [LM Studio](https://lmstudio.ai) extracts the foods, from French or English speech.
  Photos go to a vision model instead.
- Ingredient candidates come from the public ingredient search, never from the model.
- The result is sealed to the phone's inbox key and deposited in the user's
  [vault](https://github.com/pocket-nutrition/vault). When no vault was requested, or the deposit fails, it
  goes back to the recognition server instead.
- It handles one job at a time.

## Why it is safe to run at home

The Mac sits on your home or office network, so the worker accepts no incoming connection and treats
everything it processes as untrusted.

- **Outgoing calls only.** It opens no port and runs no server. It calls the recognition server, the model
  server (on this Mac by default), the public ingredient search and the user's vault. Handy runs as a command,
  not as a service.
- **Its own key.** It authenticates with `WORKER_KEY`, never with a phone's key. `deploy/launchd.sh install`
  sets `.env` to `chmod 600` and never writes the key into the launchd plist.
- **Audio and photos are untrusted.** ffmpeg decodes them with `-protocol_whitelist file`, in a private
  temporary directory that is deleted afterwards, and audio is cut at a maximum duration. A photo is
  re-encoded as a size-bounded JPEG without metadata before any model sees it. Neither is ever kept.
- **Transcripts are untrusted text.** The models are told to ignore instructions found in a transcript or in
  text written on a photo. Their answers are validated (allowed values only, bounded numbers, capped item
  count), and candidates come only from the ingredient search.
- **The vault address is untrusted.** It comes from a phone, so the worker refuses anything that is not
  `https`, any host that resolves to a private or local address, and any redirect: a stranger's address should
  not be a way into your network. The one exception is `WORKER_VAULT_TRUSTED_HOSTS`, a list only you can set,
  for a vault you run whose name resolves to a private address on your own network.
- **Failure reasons carry no content.** What the server and the phone learn about a failed job is an error
  type (for example `ExtractionError`) or "no speech detected", never an exception message, which could
  contain what was said.

Two things to know. The worker has to read each recording and photo to process it, so they are not end-to-end
encrypted to it. And the transcript and the photo are sent to the model server at `WORKER_LLM_URL`, which is
LM Studio on the same Mac by default: keep it there if you want them to stay on that machine. Error details in
the log can contain fragments of what was said, and they stay on the Mac.

## Requirements

- macOS on Apple silicon
- Python 3.12 (`brew install python@3.12`)
- ffmpeg (`brew install ffmpeg`)
- [Handy](https://handy.computer), with the Cohere Transcribe model downloaded in it
- [LM Studio](https://lmstudio.ai), with its local server running and a model loaded. To process photos the
  model must accept images, or you set `WORKER_VISION_MODEL` to one that does. [.env.example](.env.example)
  suggests `google/gemma-4-e4b`.
- A recognition server you run, and the worker key it expects (see below)

## Install

```bash
git clone https://github.com/pocket-nutrition/recognition-worker-osx.git
cd recognition-worker-osx
./setup.sh                    # creates .venv, installs the dependencies, copies .env.example to .env
```

Edit `.env`:

- `WORKER_SERVER_URL`: the address of your recognition server.
- `WORKER_KEY`: the same value as that server's `RECOGNITION_WORKER_KEY` (16 characters or more, and different
  from the server's API key). The server must run in worker mode (`RECOGNITION_PIPELINE=worker`).

Check that Handy has the Cohere Transcribe model and that LM Studio's local server is running with your model
loaded. Then install the worker as a launchd agent:

```bash
deploy/launchd.sh install     # starts at login, restarts after a crash
deploy/launchd.sh status      # state, pid and last exit code
deploy/launchd.sh logs        # follows ~/Library/Logs/recognition-worker.log
deploy/launchd.sh uninstall   # stops it and removes the agent
```

`install` refuses to run without a `.env` and a `WORKER_KEY` of 16 characters or more. The agent does not
start LM Studio for you: if the model server is down, jobs fail at extraction.

To try it in the foreground first, run `.venv/bin/python -m worker.main`. When the apps send a recording or a
photo, the log shows `processing ticket ...`.

The server side is [`recognition`](https://github.com/pocket-nutrition/recognition).

## Configuration

All settings are environment variables prefixed with `WORKER_`, read from `.env`.
[.env.example](.env.example) lists every setting you would normally change, with its default and a one-line
description. The ones you will most likely touch:

| Variable | Description |
|----------|-------------|
| `WORKER_SERVER_URL` | Address of your recognition server (required) |
| `WORKER_KEY` | Your server's `RECOGNITION_WORKER_KEY` (required, secret) |
| `WORKER_LLM_URL`, `WORKER_LLM_MODEL` | The OpenAI-compatible model server (LM Studio listens on port 1234) and the model that extracts the foods |
| `WORKER_VISION_MODEL` | The model that reads photos; it must accept images. Empty means `WORKER_LLM_MODEL` |
| `WORKER_VISION_LANGUAGE` | `fr` or `en`: the language photo queries are written in, since a photo carries no language |
| `WORKER_HANDY_BIN`, `WORKER_HANDY_MODEL` | Where Handy is installed, and which of its models transcribes |
| `WORKER_API_URL` | The ingredient search that supplies candidates (the public Pocket Nutrition API by default) |
| `WORKER_VAULT_TRUSTED_HOSTS` | Vault hosts you run that may resolve to a private address (empty by default) |

## Troubleshooting

When a job fails, the app only sees an error type. The details are in the log (`deploy/launchd.sh logs`).

- `ExtractionError`: LM Studio's server is not running, the model is not loaded (or does not accept images,
  for a photo), or its answer was not usable.
- `TranscriptionError`: Handy did not answer in time or failed, or ffmpeg could not decode the clip.
- `FileNotFoundError`: Handy or ffmpeg was not found at `WORKER_HANDY_BIN` or `WORKER_FFMPEG_BIN`.
- `ImageError`: ffmpeg could not convert the photo.
- `no speech detected`: the recording is silent, or Handy returned no text.
- The log repeats `claim failed (...)`: the worker cannot reach the server (`ConnectError`), or the server
  refuses it (`HTTPStatusError`: a `WORKER_KEY` that does not match, a server not in worker mode, or a
  `WORKER_CLAIM_WAIT_S` above the server's maximum wait of 25 seconds).

## Testing

```bash
.venv/bin/pytest
```

The suite needs no network, Handy, LM Studio or recognition server: every call out is mocked. Two tests run
the real `ffmpeg` and `ffprobe`, and are skipped when ffmpeg is missing.

## Using with Claude Code

This project includes a [CLAUDE.md](CLAUDE.md) that gives Claude Code full context on the processing flow,
the security invariants and the commands.

```bash
claude    # Start Claude Code — reads CLAUDE.md automatically
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing expectations, and the PR workflow.

## License

AGPL-3.0 — see [LICENSE](LICENSE).
