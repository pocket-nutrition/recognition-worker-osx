---
name: Bug report
about: Report a job that failed, a wrong result, or a worker that will not install or start
title: "[Bug] "
labels: bug
assignees: ''
---

<!--
Before you post:
- Never paste your WORKER_KEY, a vault URL or token, a transcript or a photo.
- Error details in the log can contain fragments of what was said or shown: redact them.
- Security problems (for example a way to make the worker call into a private network, or to expose
  audio, photos or transcripts) do not belong in a public issue. Use "Report a vulnerability" on this
  repository's Security tab instead.
-->

## Describe the bug

A clear and concise description of what is wrong.

## What the worker was processing

- [ ] A recording
- [ ] A photo
- [ ] Nothing: it fails to install or start

## Steps to reproduce

1. ...
2. ...

## Expected behavior

What you expected instead, and why.

## Actual behavior

What happened. If the app showed a failure reason, quote it: it is only an error type (for example
`ExtractionError`) or `no speech detected`.

## Log output

The relevant lines, redacted as described above. Use `deploy/launchd.sh logs`, or the terminal if you ran
`.venv/bin/python -m worker.main`.

```text
```

## Environment

- Worker version / commit: `git rev-parse HEAD`
- macOS version and chip (for example macOS 15, Apple M2)
- Python version: `.venv/bin/python --version`
- Handy version, and the value of `WORKER_HANDY_MODEL`
- LM Studio version, and the models set in `WORKER_LLM_MODEL` and `WORKER_VISION_MODEL`
- ffmpeg version: `ffmpeg -version | head -1`
- How you run the worker: launchd agent (`deploy/launchd.sh install`) or foreground
- Version or commit of the recognition server you point it at

## Additional context

Add any other context about the problem here.
