#!/usr/bin/env bash
# Start Google Chrome with CDP (delegates to launch_chrome_cdp.py).
#
# Usage (from repo root):
#   ./scripts/launch_chrome_cdp.sh
#   ./scripts/launch_chrome_cdp.sh --port 9223
#
# Works in bash and zsh (default Terminal shell on macOS).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

exec python scripts/launch_chrome_cdp.py "$@"
