#!/bin/sh
set -eu
cd "$(dirname "$0")"
npm --prefix orchestrator ci --no-audit --no-fund
npm --prefix orchestrator run build
cp orchestrator/node_modules/zod/LICENSE orchestrator/dist/zod.LICENSE
mkdir -p frontend/dist
cp frontend/src/index.html frontend/src/app.js frontend/src/styles.css frontend/dist/
