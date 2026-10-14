#!/usr/bin/env bash
# Delegado fino: la captura vive en `radar refresh` (src/radar/capture.py), que es multiplataforma.
# Este script solo fija el registro y lo invoca desde el servicio de systemd.
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RADAR_BIN="${RADAR_BIN:-$PROJECT_DIR/.venv/bin/radar}"
STATE_DIR="${RADAR_STATE_DIR:-$HOME/.local/state/radar}"

mkdir -p "$STATE_DIR"
cd "$PROJECT_DIR"
"$RADAR_BIN" refresh "$@" >> "$STATE_DIR/refresh.log" 2>&1
