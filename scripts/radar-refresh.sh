#!/usr/bin/env bash
set -uo pipefail

PROJECT_DIR="/home/paolo/Projects/Radar"
JOBSPY_BIN="$PROJECT_DIR/.venv-jobspy/bin/radar"
RADAR_BIN="$PROJECT_DIR/.venv/bin/radar"
STATE_DIR="/home/paolo/.local/state/radar"
# The scheduled view favors freshness; override with RADAR_MAX_AGE_DAYS when
# a wider market snapshot is intentionally needed.
MAX_AGE_DAYS="${RADAR_MAX_AGE_DAYS:-10}"
COMPUTRABAJO_ENABLED="${RADAR_COMPUTRABAJO_ENABLED:-1}"
# LinkedIn via jobspy validated 2026-09-18 (public search results, no login).
export RADAR_JOBSPY_SITES="${RADAR_JOBSPY_SITES:-indeed,linkedin}"
STALE_AFTER_DAYS="${RADAR_STALE_AFTER_DAYS:-45}"
LIVENESS_CHECK_LIMIT="${RADAR_LIVENESS_CHECK_LIMIT:-150}"
# Lima es el mercado predeterminado. La cobertura nacional se habilita explícitamente
# definiendo RADAR_CITIES con una lista separada por comas.
CITIES="${RADAR_CITIES-}"

mkdir -p "$STATE_DIR"
cd "$PROJECT_DIR"

FAILED_STEPS=()

# Every step is best-effort (one source timing out must not block the rest),
# but silently swallowing errors with `|| true` made failures invisible.
# This wraps each step so failures are still logged and summarized at the end.
run_step() {
    local label="$1"
    shift
    echo "[$label]"
    "$@"
    local status=$?
    if [[ $status -ne 0 ]]; then
        echo "[$label] FAILED (exit $status)"
        FAILED_STEPS+=("$label")
    fi
}

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
        run_step "jobspy/indeed+linkedin: $query" \
            timeout 180 "$JOBSPY_BIN" ingest --source jobspy --query "$query" \
                --location Lima --limit 50 --max-age-days "$MAX_AGE_DAYS"
    done

    # Detail extractor validated 2026-09-18 against real offers (100% full
    # descriptions on backfill); scheduled cycle is active by default.
    if [[ "$COMPUTRABAJO_ENABLED" == "1" ]]; then
        for query in "${queries[@]}"; do
            run_step "computrabajo: $query" \
                timeout 180 "$RADAR_BIN" ingest --source computrabajo --query "$query" \
                    --location Lima --limit 50 --max-age-days "$MAX_AGE_DAYS"
        done
    else
        echo "[computrabajo] scheduled cycle paused; set RADAR_COMPUTRABAJO_ENABLED=1 after detail validation"
    fi

    city_queries=(
        "logistica inventarios almacenes"
        "produccion operaciones industrial"
        "calidad Lean Six Sigma"
        "procesos BPMN mejora continua"
    )
    IFS=',' read -ra city_list <<< "$CITIES"
    for city in "${city_list[@]}"; do
        [[ -z "$city" ]] && continue
        for query in "${city_queries[@]}"; do
            run_step "jobspy/indeed+linkedin [$city]: $query" \
                timeout 180 "$JOBSPY_BIN" ingest --source jobspy --query "$query" \
                    --location "$city" --limit 25 --max-age-days "$MAX_AGE_DAYS"
            if [[ "$COMPUTRABAJO_ENABLED" == "1" ]]; then
                run_step "computrabajo [$city]: $query" \
                    timeout 180 "$RADAR_BIN" ingest --source computrabajo --query "$query" \
                        --location "$city" --limit 25 --max-age-days "$MAX_AGE_DAYS"
            fi
        done
    done

    run_step "quality: repair-data" "$RADAR_BIN" repair-data
    run_step "quality: expire-stale" "$RADAR_BIN" expire-stale --days "$STALE_AFTER_DAYS"
    run_step "quality: check-applications" "$RADAR_BIN" check-applications --limit "$LIVENESS_CHECK_LIMIT"
    run_step "market: snapshot" "$RADAR_BIN" market-snapshot

    if [[ ${#FAILED_STEPS[@]} -gt 0 ]]; then
        echo "SUMMARY: ${#FAILED_STEPS[@]} step(s) failed: ${FAILED_STEPS[*]}"
    else
        echo "SUMMARY: all steps completed"
    fi
    date --iso-8601=seconds
} >> "$STATE_DIR/refresh.log" 2>&1
