#!/usr/bin/env bash
set -euo pipefail

# Generic wrapper for api_jira.py commands (Linux/macOS).
# Run from skill root or scripts/:
#   bash scripts/deploy.sh config show
#   bash scripts/deploy.sh copy-log-from-description --issue X6873OS162-1079 --http-only

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python}"
if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python3
fi
exec "$PY" "${SCRIPT_DIR}/api_jira.py" "$@"

