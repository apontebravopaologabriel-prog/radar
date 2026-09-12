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

if ! /usr/bin/curl -fsS --max-time 2 "$API_URL" >/dev/null 2>&1; then
    if ! /usr/bin/docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d postgres >>"$STATE_DIR/launcher.log" 2>&1; then
        notify_error "No se pudo iniciar PostgreSQL. Revisa Docker."
        exit 1
    fi

    database_ready=0
    for _ in $(seq 1 30); do
        if /usr/bin/docker compose -f "$PROJECT_DIR/docker-compose.yml" exec -T postgres pg_isready -U radar -d radar >/dev/null 2>&1; then
            database_ready=1
            break
        fi
        sleep 1
    done
    if [ "$database_ready" -ne 1 ]; then
        notify_error "PostgreSQL no estuvo listo a tiempo."
        exit 1
    fi

    cd "$PROJECT_DIR" || exit 1
    nohup "$PROJECT_DIR/.venv/bin/radar-api" >>"$STATE_DIR/api.log" 2>&1 &
    api_ready=0
    for _ in $(seq 1 30); do
        if /usr/bin/curl -fsS --max-time 2 "$API_URL" >/dev/null 2>&1; then
            api_ready=1
            break
        fi
        sleep 1
    done
    if [ "$api_ready" -ne 1 ]; then
        notify_error "La API de Radar no pudo iniciar. Revisa $STATE_DIR/api.log"
        exit 1
    fi
fi

if ! /usr/bin/curl -fsS --max-time 2 "$APP_URL" >/dev/null 2>&1; then
    cd "$PROJECT_DIR/frontend" || exit 1
    nohup /usr/bin/npm run dev -- --hostname 127.0.0.1 --port "$FRONTEND_PORT" >>"$STATE_DIR/frontend.log" 2>&1 &
    frontend_ready=0
    for _ in $(seq 1 45); do
        if /usr/bin/curl -fsS --max-time 2 "$APP_URL" >/dev/null 2>&1; then
            frontend_ready=1
            break
        fi
        sleep 1
    done
    if [ "$frontend_ready" -ne 1 ]; then
        notify_error "El frontend de Radar no pudo iniciar. Revisa $STATE_DIR/frontend.log"
        exit 1
    fi
fi

CHROMIUM_PROFILE="$STATE_DIR/chromium"
exec /usr/bin/chromium \
    --app="$APP_URL" \
    --class=Radar \
    --name=Radar \
    --user-data-dir="$CHROMIUM_PROFILE"
