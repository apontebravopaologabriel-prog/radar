#!/usr/bin/env bash

set -u

PROJECT_DIR="/home/paolo/Projects/Radar"
STATE_DIR="/home/paolo/.local/state/radar"
FRONTEND_OUT="$PROJECT_DIR/frontend/out"
API_URL="http://127.0.0.1:8100/api/health"
APP_URL="http://127.0.0.1:8100/radar"

mkdir -p "$STATE_DIR"

notify_error() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send --urgency=critical "Radar" "$1"
    fi
}

build_frontend_if_needed() {
    if [ -f "$FRONTEND_OUT/radar.html" ] && [ -d "$FRONTEND_OUT/_next" ]; then
        newest_source=$(find \
            "$PROJECT_DIR/frontend/app" \
            "$PROJECT_DIR/frontend/components" \
            "$PROJECT_DIR/frontend/lib" \
            "$PROJECT_DIR/frontend/types.ts" \
            "$PROJECT_DIR/frontend/next.config.ts" \
            -type f -newer "$FRONTEND_OUT/radar.html" -print -quit)
        if [ -z "$newest_source" ]; then
            return 0
        fi
    fi

    (
        cd "$PROJECT_DIR/frontend" || exit 1
        /usr/bin/npm run build >>"$STATE_DIR/frontend.log" 2>&1
    )
}

start_api() {
    cd "$PROJECT_DIR" || exit 1
    nohup "$PROJECT_DIR/.venv/bin/radar-api" >>"$STATE_DIR/api.log" 2>&1 &
    api_ready=0
    for _ in $(seq 1 15); do
        if /usr/bin/curl -fsS --max-time 1 "$API_URL" >/dev/null 2>&1; then
            api_ready=1
            break
        fi
        sleep 0.3
    done
    if [ "$api_ready" -ne 1 ]; then
        notify_error "La API de Radar no pudo iniciar. Revisa $STATE_DIR/api.log"
        exit 1
    fi
}

# FastAPI sirve la aplicación estática. El build debe existir antes de importar
# radar.api, porque las rutas /radar y /_next se registran al arrancar la API.
if ! build_frontend_if_needed; then
    notify_error "El frontend de Radar no pudo compilar. Revisa $STATE_DIR/frontend.log"
    exit 1
fi

# Una API que sigue corriendo con código anterior responde a /api/health pero devuelve 404 en las
# rutas nuevas. Si algún módulo de src/radar es más nuevo que el proceso, se reinicia.
restart_api_if_stale() {
    api_pid=$(/usr/bin/pgrep -f "$PROJECT_DIR/.venv/bin/radar-api" | head -n 1)
    [ -n "$api_pid" ] || return 0
    stale_source=$(find "$PROJECT_DIR/src/radar" -name '*.py' -newer "/proc/$api_pid" -print -quit)
    if [ -n "$stale_source" ]; then
        pkill -f "$PROJECT_DIR/.venv/bin/radar-api" 2>/dev/null || true
        sleep 1
    fi
}
restart_api_if_stale

# Mantener la API viva al cerrar Chromium evita dejar una ventana estática sin
# backend. El siguiente lanzamiento solo la inicia si realmente no responde.
if ! /usr/bin/curl -fsS --max-time 2 "$API_URL" >/dev/null 2>&1; then
    start_api
fi

if ! /usr/bin/curl -fsS --max-time 2 "$APP_URL" >/dev/null 2>&1; then
    # Recuperar una instancia antigua de radar-api que responda en /api/health
    # pero todavía no conozca las rutas del frontend estático.
    pkill -f "$PROJECT_DIR/.venv/bin/radar-api" 2>/dev/null || true
    start_api
fi

if ! /usr/bin/curl -fsS --max-time 2 "$APP_URL" >/dev/null 2>&1; then
    notify_error "La interfaz de Radar no está disponible. Revisa $STATE_DIR/api.log"
    exit 1
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

# radar-api queda activo para que una ventana reutilizada de Chromium no pierda
# el backend al terminar este script.
