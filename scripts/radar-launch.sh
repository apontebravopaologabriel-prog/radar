#!/usr/bin/env bash

set -u

PROJECT_DIR="/home/paolo/Projects/Radar"
STATE_DIR="/home/paolo/.local/state/radar"
API_URL="http://127.0.0.1:8100/api/health"
FRONTEND_PORT=3000
APP_URL="http://127.0.0.1:${FRONTEND_PORT}/radar"

mkdir -p "$STATE_DIR"

notify_error() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send --urgency=critical "Radar" "$1"
    fi
}

cleanup() {
    pkill -f "next-server" 2>/dev/null || true
    pkill -f "npm run start.*--port $FRONTEND_PORT" 2>/dev/null || true
    pkill -f "$PROJECT_DIR/.venv/bin/radar-api" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Iniciar la API local si no responde
if ! /usr/bin/curl -fsS --max-time 2 "$API_URL" >/dev/null 2>&1; then
    cd "$PROJECT_DIR" || exit 1
    nohup "$PROJECT_DIR/.venv/bin/radar-api" >>"$STATE_DIR/api.log" 2>&1 &
    api_ready=0
    for _ in $(seq 1 15); do
        if /usr/bin/curl -fsS --max-time 1 "$API_URL" >/dev/null 2>&1; then
            api_ready=1
            break
        fi
        sleep 0.5
    done
    if [ "$api_ready" -ne 1 ]; then
        notify_error "La API de Radar no pudo iniciar. Revisa $STATE_DIR/api.log"
        exit 1
    fi
fi

# Iniciar el frontend de Next.js si no responde
if ! /usr/bin/curl -fsS --max-time 2 "$APP_URL" >/dev/null 2>&1; then
    cd "$PROJECT_DIR/frontend" || exit 1
    if [ ! -d "$PROJECT_DIR/frontend/.next" ]; then
        /usr/bin/npm run build >>"$STATE_DIR/frontend.log" 2>&1
    fi
    nohup /usr/bin/npm run start -- --hostname 127.0.0.1 --port "$FRONTEND_PORT" >>"$STATE_DIR/frontend.log" 2>&1 &
    frontend_ready=0
    for _ in $(seq 1 45); do
        if /usr/bin/curl -fsS --max-time 1 "$APP_URL" >/dev/null 2>&1; then
            frontend_ready=1
            break
        fi
        sleep 0.5
    done
    if [ "$frontend_ready" -ne 1 ]; then
        notify_error "El frontend de Radar no pudo iniciar. Revisa $STATE_DIR/frontend.log"
        exit 1
    fi
fi

CHROMIUM_PROFILE="$STATE_DIR/chromium"
/usr/bin/chromium \
    --app="$APP_URL" \
    --class=Radar \
    --name=Radar \
    --ozone-platform=wayland \
    --enable-features=VaapiVideoDecodeLinuxGL,TouchpadOverscrollHistoryNavigation \
    --ignore-gpu-blocklist \
    --enable-gpu-rasterization \
    --enable-zero-copy \
    --user-data-dir="$CHROMIUM_PROFILE"

# Al cerrar la ventana, la función trap cleanup liberará todos los procesos de fondo
