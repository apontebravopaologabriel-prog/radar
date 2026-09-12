#!/usr/bin/env bash
set -uo pipefail

PROJECT_DIR="/home/paolo/Projects/Radar"
JOBSPY_BIN="$PROJECT_DIR/.venv-jobspy/bin/radar"
RADAR_BIN="$PROJECT_DIR/.venv/bin/radar"
STATE_DIR="/home/paolo/.local/state/radar"
MAX_AGE_DAYS="${RADAR_MAX_AGE_DAYS:-14}"

mkdir -p "$STATE_DIR"
cd "$PROJECT_DIR"

{
    date --iso-8601=seconds
    echo "Radar refresh: max_age_days=$MAX_AGE_DAYS"

    # Each query is independent: a source timeout must not block the rest.
    queries=(
        "procesos automatizacion"
        "analista datos BI SQL Power BI"
        "mejora continua calidad"
        "produccion planeamiento industrial"
        "logistica operaciones supply chain"
        "compras abastecimiento"
        "sistemas ERP automatizacion"
        "proyectos PMO industrial"
    )
    for query in "${queries[@]}"; do
        echo "[jobspy] $query"
        timeout 180 "$JOBSPY_BIN" ingest --source jobspy --query "$query" \
            --location Lima --limit 25 --max-age-days "$MAX_AGE_DAYS" || true
    done

    echo "[quality] repair-data"
    "$RADAR_BIN" repair-data || true
    echo "[market] snapshot"
    "$RADAR_BIN" market-snapshot || true
    date --iso-8601=seconds
} >> "$STATE_DIR/refresh.log" 2>&1
