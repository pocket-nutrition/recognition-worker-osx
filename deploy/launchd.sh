#!/bin/sh
# Install, remove or inspect the worker as a per-user launchd agent (starts at login, restarts on crash).
#
#   deploy/launchd.sh install | uninstall | status | logs
set -eu

LABEL=org.pocketnutrition.recognition-worker
WORKER_DIR=$(cd "$(dirname "$0")/.." && pwd)
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs"
DOMAIN="gui/$(id -u)"

case "${1:-}" in
install)
    [ -x "$WORKER_DIR/.venv/bin/python" ] || { echo "missing $WORKER_DIR/.venv: see CLAUDE.md (Dev)" >&2; exit 1; }
    [ -f "$WORKER_DIR/.env" ] || { echo "missing $WORKER_DIR/.env: copy .env.example and set WORKER_KEY" >&2; exit 1; }
    grep -q '^WORKER_KEY=.\{16,\}' "$WORKER_DIR/.env" || { echo "WORKER_KEY in .env must be set (16+ characters)" >&2; exit 1; }
    # The key is a credential: only this user may read it.
    chmod 600 "$WORKER_DIR/.env"
    mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
    sed -e "s|__WORKER_DIR__|$WORKER_DIR|g" -e "s|__LOG_DIR__|$LOG_DIR|g" \
        "$WORKER_DIR/deploy/$LABEL.plist.template" > "$PLIST"
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "installed: $PLIST"
    echo "logs: $LOG_DIR/recognition-worker.log"
    ;;
uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "removed $LABEL"
    ;;
status)
    launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E "state|pid|last exit code" || echo "not loaded"
    ;;
logs)
    tail -f "$LOG_DIR/recognition-worker.log"
    ;;
*)
    echo "usage: $0 install | uninstall | status | logs" >&2
    exit 2
    ;;
esac
