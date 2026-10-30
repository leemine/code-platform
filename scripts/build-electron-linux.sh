#!/usr/bin/env bash
# Build the existing Electron shell and frozen backend on Linux.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${1:-external}"
case "$PROFILE" in native|external) ;; *) echo 'usage: build-electron-linux.sh [external|native]' >&2; exit 2;; esac
[ "$(uname -s)" = Linux ] || { echo 'Run this build on Linux.' >&2; exit 2; }
cd "$ROOT"
UV="${UV:-uv}"
args=(sync --locked --no-default-groups --extra dev --no-editable)
if [ "$PROFILE" = native ]; then args+=(--extra native --group dev); fi
"$UV" "${args[@]}"
PY="$ROOT/.venv/bin/python"
"$PY" scripts/build_config.py --sync
FRONTEND="$ROOT/jiuwenswarm/channels/web/frontend"
DESKTOP="$ROOT/jiuwenswarm/channels/desktop/electron"
(cd "$FRONTEND" && npm ci --no-audit --no-fund && ELECTRON=true npx --no-install vite build --base=/)
(cd "$DESKTOP" && npm ci --no-audit --no-fund && node node_modules/electron/install.js)
export JIUWENSWARM_BUILD_PROFILE="$PROFILE"
"$PY" -m PyInstaller scripts/jiuwenswarm.spec --noconfirm
if [ "$PROFILE" = external ]; then
    "$ROOT/dist/workswarm/workswarm" "$ROOT/scripts/verify_external_bundle.py"
fi
"$PY" scripts/assemble-electron-linux.py --profile "$PROFILE"
