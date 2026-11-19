#!/usr/bin/env bash
# Run the job agent once. Used by cron.
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m jobagent run "$@"
