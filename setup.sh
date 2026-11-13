#!/usr/bin/env bash
set -euo pipefail

# Pocket Nutrition Recognition Worker — First-time setup
# Usage: ./setup.sh

cd "$(dirname "${BASH_SOURCE[0]}")"

echo "=== Pocket Nutrition Recognition Worker Setup ==="

# Check prerequisites
command -v python3.12 >/dev/null 2>&1 || { echo "Error: python3.12 is required (macOS: brew install python@3.12)."; exit 1; }

# Virtual environment
if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python3.12 -m venv .venv
fi

# Environment
if [ ! -f .env ]; then
  cp .env.example .env
  # The worker's key goes in this file: only this user may read it.
  chmod 600 .env
  echo "Created .env from .env.example — edit it with your values"
fi

# Dependencies
echo "Installing dependencies..."
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements-dev.txt

# Needed to run jobs, not to install or to run the tests, so this only warns.
command -v ffmpeg >/dev/null 2>&1 || echo "Warning: ffmpeg was not found on PATH. Running jobs needs it (macOS: brew install ffmpeg), or set WORKER_FFMPEG_BIN in .env."

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env: set WORKER_SERVER_URL (your recognition server) and WORKER_KEY (that server's"
echo "     RECOGNITION_WORKER_KEY)"
echo "  2. Install Handy with the Cohere Transcribe model, and start LM Studio's local server with a model loaded"
echo "  3. Run in the foreground: .venv/bin/python -m worker.main"
echo "     or start it at login:  deploy/launchd.sh install"
echo "  4. Run tests: .venv/bin/pytest"
echo "  5. Using Claude Code? CLAUDE.md has all the context."
