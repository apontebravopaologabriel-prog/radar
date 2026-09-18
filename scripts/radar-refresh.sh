#!/usr/bin/env bash
set -uo pipefail

PROJECT_DIR="/home/paolo/Projects/Radar"
JOBSPY_BIN="$PROJECT_DIR/.venv-jobspy/bin/radar"
RADAR_BIN="$PROJECT_DIR/.venv/bin/radar"
STATE_DIR="/home/paolo/.local/state/radar"
# The scheduled view favors freshness; override with RADAR_MAX_AGE_DAYS when
# a wider market snapshot is intentionally needed.
MAX_AGE_DAYS="${RADAR_MAX_AGE_DAYS:-7}"
COMPUTRABAJO_ENABLED="${RADAR_COMPUTRABAJO_ENABLED:-1}"

mkdir -p "$STATE_DIR"
cd "$PROJECT_DIR"

{
    date --iso-8601=seconds
    echo "Radar refresh: max_age_days=$MAX_AGE_DAYS"

    # Broad market capture: salary is never an ingestion criterion. Each query
    # is independent so a source timeout does not block the rest.
    queries=(
        "analista datos BI SQL Power BI"
        "analista data analytics Python"
        "procesos BPMN mejora continua"
        "automatizacion Python RPA Power Automate"
        "transformacion digital industrial"
        "analista funcional ERP sistemas"
        "soporte aplicaciones ERP SQL"
        "planeamiento demanda forecast"
        "planner supply chain abastecimiento"
        "logistica inventarios almacenes"
        "compras procurement abastecimiento"
        "produccion operaciones industrial"
        "calidad Lean Six Sigma"
        "mantenimiento industrial operaciones"
        "control de gestion indicadores"
        "proyectos PMO industrial"
    )
    for query in "${queries[@]}"; do
        echo "[jobspy/indeed] $query"
        timeout 180 "$JOBSPY_BIN" ingest --source jobspy --query "$query" \
            --location Lima --limit 50 --max-age-days "$MAX_AGE_DAYS" || true
    done

    # Detail extractor validated 2026-09-18 against real offers (100% full
    # descriptions on backfill); scheduled cycle is active by default.
    if [[ "$COMPUTRABAJO_ENABLED" == "1" ]]; then
        for query in "${queries[@]}"; do
            echo "[computrabajo] $query"
            timeout 180 "$RADAR_BIN" ingest --source computrabajo --query "$query" \
                --location Lima --limit 50 --max-age-days "$MAX_AGE_DAYS" || true
        done
    else
        echo "[computrabajo] scheduled cycle paused; set RADAR_COMPUTRABAJO_ENABLED=1 after detail validation"
    fi

    echo "[quality] repair-data"
    "$RADAR_BIN" repair-data || true
    echo "[market] snapshot"
    "$RADAR_BIN" market-snapshot || true
    date --iso-8601=seconds
} >> "$STATE_DIR/refresh.log" 2>&1
