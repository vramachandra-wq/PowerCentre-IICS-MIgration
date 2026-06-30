#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

MODE="${MODE:-all}"
CONFIG="${CONFIG:-common/config/config.json}"
PID_FILE="${PID_FILE:-output/app.pid}"
LOG_FILE="${LOG_FILE:-output/app_start.log}"
EXTRA_ARGS="${EXTRA_ARGS:-}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  fail "Python is not installed or not available on PATH."
fi

[[ -f "app.py" ]] || fail "app.py was not found. Run this script from the project root."
[[ -f "$CONFIG" ]] || fail "Configuration file not found: $CONFIG"
[[ -d "input_xml" ]] || fail "Input XML folder not found: input_xml"

mkdir -p "$(dirname "$PID_FILE")" "$(dirname "$LOG_FILE")"

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$EXISTING_PID" ]] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    fail "Application is already running with PID $EXISTING_PID."
  fi
  rm -f "$PID_FILE"
fi

echo "Starting PowerCenter to IICS workflow..."
echo "Mode: $MODE"
echo "Config: $CONFIG"
echo "Log: $LOG_FILE"

nohup "$PYTHON_BIN" app.py --mode "$MODE" --config "$CONFIG" $EXTRA_ARGS >"$LOG_FILE" 2>&1 &
APP_PID="$!"
echo "$APP_PID" >"$PID_FILE"

sleep 1
if ! kill -0 "$APP_PID" 2>/dev/null; then
  rm -f "$PID_FILE"
  echo "Application failed to start. Last log lines:" >&2
  tail -n 40 "$LOG_FILE" >&2 || true
  exit 1
fi

echo "Application started with PID $APP_PID."
