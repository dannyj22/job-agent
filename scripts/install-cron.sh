#!/usr/bin/env bash
# Install (or refresh) a cron job that runs the agent every 3 hours.
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT/.venv/bin/python"
LOG_DIR="$PROJECT/logs"
mkdir -p "$LOG_DIR"

if [ ! -x "$PYTHON" ]; then
  echo "Python venv not found at $PYTHON"
  echo "Run: cd \"$PROJECT\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

SCHEDULE="${1:-0 */3 * * *}"
CRON_LINE="$SCHEDULE cd \"$PROJECT\" && \"$PYTHON\" -m jobagent run >> \"$LOG_DIR/cron.log\" 2>&1"

# Keep any existing entries, replace only ours.
( crontab -l 2>/dev/null | grep -v "jobagent run" || true; echo "$CRON_LINE" ) | crontab -

echo "Installed cron entry:"
echo "  $CRON_LINE"
echo
echo "View it with: crontab -l"
echo "Remove it with: crontab -e"
