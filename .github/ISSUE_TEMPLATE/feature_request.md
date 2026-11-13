---
name: Feature request
about: Suggest an idea or improvement for this worker
title: "[Feature] "
labels: enhancement
assignees: ''
---

## Is your feature request related to a problem?

A clear and concise description of what the problem is (e.g. "I'm always frustrated
when...").

## Describe the solution you'd like

A clear and concise description of what you want to happen. If it adds a setting, or changes what the
worker exchanges with the recognition server or the vault (the shapes in `worker/schemas.py`), include an
example.

## Describe alternatives you've considered

Any alternative solutions or features you've considered.

## Scope check

- [ ] This does not need the worker to accept incoming connections: it only makes outgoing calls.
- [ ] This does not need the worker to keep audio, photos or transcripts.
- [ ] This does not loosen how the worker treats audio, photos, transcripts and the vault address as
      untrusted (see "Invariants" in `CLAUDE.md`).
- [ ] This does not need the worker to hold nutrition data: ingredient candidates come from the public
      ingredient search, never from the model.

## Additional context

Add any other context, references, or screenshots about the feature request here.
