#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PID_FILE="${PID_FILE:-output/app.pid}"

if [[ ! -f "$PID_FILE" ]]; then
  echo "Application is not running: no PID file found."
  exit 0
fi

APP_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "$APP_PID" ]]; then
  echo "PID file is empty. Removing stale PID file."
  rm -f "$PID_FILE"
  exit 0
fi

if ! kill -0 "$APP_PID" 2>/dev/null; then
  echo "Application is not running. Removing stale PID file for PID $APP_PID."
  rm -f "$PID_FILE"
  exit 0
fi

echo "Stopping application with PID $APP_PID..."
kill "$APP_PID" 2>/dev/null || true

for _ in $(seq 1 15); do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "Application stopped."
    exit 0
  fi
  sleep 1
done

echo "Application did not stop after SIGTERM; sending SIGKILL."
kill -9 "$APP_PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "Application stopped."
