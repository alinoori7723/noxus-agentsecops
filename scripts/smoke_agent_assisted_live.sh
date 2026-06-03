#!/usr/bin/env bash
#
# Optional MANUAL live smoke for Agent-Assisted mode (NOT part of pytest).
#
# Thin wrapper: all logic lives in the importable, testable companion
# scripts/smoke_agent_assisted_live.py (stdlib only). Secrets travel via
# environment variables, never argv; the Python program never prints the API
# key and redacts it in error text. See that file for required env vars and
# exit codes.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${DIR}/smoke_agent_assisted_live.py" "$@"
