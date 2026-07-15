#!/usr/bin/env bash
# TongLing Web standalone launcher (Linux / macOS)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export TONGLING_ROOT="$ROOT"
export TONGLING_LAUNCH_MODE="${TONGLING_LAUNCH_MODE:-web-standalone}"

# Non-interactive shells often miss Node (nvm/fnm/volta)
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ -s "$NVM_DIR/nvm.sh" ]; then
  # shellcheck disable=SC1090
  . "$NVM_DIR/nvm.sh"
fi
if command -v fnm >/dev/null 2>&1; then
  eval "$(fnm env --shell bash 2>/dev/null || true)"
fi
if [ -d "$HOME/.volta/bin" ]; then
  export PATH="$HOME/.volta/bin:$PATH"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] Python 3.10+ required" >&2
  exit 1
fi

if ! python3 -c "import flask" 2>/dev/null; then
  bash "$ROOT/install-deps.sh"
fi

HS="$ROOT/storage/hexstrike-ai-community-edition-master"
if [ ! -f "$HS/hexstrike_server.py" ]; then
  echo "[WARN] HexStrike CE not found under storage/" >&2
fi

echo
echo "TongLing Web standalone - ${HEXSTRIKE_HOST:-0.0.0.0}:${HEXSTRIKE_PORT:-15038}"
echo

exec python3 "$ROOT/tongling_hexstrike_launcher.py" \
  --host "${HEXSTRIKE_HOST:-0.0.0.0}" \
  --port "${HEXSTRIKE_PORT:-15038}" \
  "$@"
