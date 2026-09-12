# Operación de Radar

## Instalación

```bash
cd /home/paolo/Projects/Radar
cp .env.example .env
docker compose up -d postgres
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Ingesta

Computrabajo:

```bash
.venv/bin/radar ingest --source computrabajo --query "practicante de procesos" --location Lima --limit 10
```

JobSpy requiere Python 3.12:

```bash
uv venv --python 3.12 .venv-jobspy
uv pip install --python .venv-jobspy/bin/python -e '.[jobspy]'
.venv-jobspy/bin/radar ingest --source jobspy --query "practicante ingeniería industrial" --location Lima --limit 10
```

## Perfil

```bash
.venv/bin/radar profile --name "Nombre" --area "Procesos" --location Lima --skill Excel=advanced --skill SQL=intermediate
```

Guardar el perfil recalcula los scores de las ofertas activas.

## Importación asistida desde portales

Para incorporar ofertas de LinkedIn, Bumeran, Laborum, Empleos Perú, Hiring Room o una página corporativa, prepara un CSV con:

```text
title,company,url,location,description,work_mode,salary_min,salary_max,salary_currency,salary_period,application_status,application_checked_at
```

Luego ejecuta:

```bash
.venv/bin/radar import-jobs --source linkedin --file ofertas.csv
```

Puedes cambiar `linkedin` por `bumeran`, `laborum`, `empleos-peru` o el nombre del ATS. Radar normaliza, clasifica, deduplica, extrae salarios desde el texto y conserva la URL original. En LinkedIn este flujo no requiere contraseña, cookie ni automatización de cuenta.

En LinkedIn, `application_status` debe ser `open` cuando la página muestre **Solicitar**; usa `closed` o `expired` si indica que ya no acepta solicitudes. `application_checked_at` debe contener la fecha y hora de la comprobación, por ejemplo `2026-09-11T17:00:00-05:00`. Radar excluye de búsquedas y recomendaciones los anuncios cerrados, vencidos o no verificados de LinkedIn. Si cambia el anuncio, vuelve a importar la misma fila para actualizar su estado; no se borra el registro histórico.

Ejemplo mínimo verificable:

```text
Practicante de Sistemas,Empresa,https://www.linkedin.com/jobs/view/123,Lima,"SQL Server y soporte",remote,,,,,open,2026-09-11T17:00:00-05:00
```

## Frescura de las ofertas

Las búsquedas automáticas usan por defecto un máximo de 14 días desde `published_at`:

```bash
.venv/bin/radar ingest --source computrabajo --query "automatización procesos" --location Lima --max-age-days 14
```

Para una revisión diaria más estricta, usa `--max-age-days 7`. Las ofertas sin fecha, futuras o fuera del rango no se muestran como recomendación. No se eliminan de PostgreSQL: permanecen disponibles para historial y análisis de mercado.

Para reparar ofertas capturadas antes de la inferencia de modalidad y sector:

```bash
.venv/bin/radar repair-data
```

## Refresco continuo

El refresco persistente se ejecuta como servicio de usuario cada seis horas. Consulta ocho familias: procesos/automatización, datos/BI, mejora continua/calidad, producción/planeamiento, logística/supply chain, compras, ERP/sistemas y proyectos/PMO.

```bash
systemctl --user status radar-refresh.timer
systemctl --user list-timers radar-refresh.timer
tail -f /home/paolo/.local/state/radar/refresh.log
```

El servicio es tolerante a fallos por consulta, usa un máximo de 14 días y guarda snapshots del mercado. No borra el histórico. Para detenerlo temporalmente: `systemctl --user disable --now radar-refresh.timer`; para reactivarlo: `systemctl --user enable --now radar-refresh.timer`.

Las ofertas incorporadas incluyen `sector`, `work_mode`, `hours_per_week`, `schedule_text` y el estado de solicitud cuando la fuente entrega evidencia suficiente. Los campos ausentes permanecen como `NULL` o `unknown`; en LinkedIn un estado `unknown` no se muestra como oferta accionable.

## Frontend y launcher

Para abrir la aplicación desde el menú del sistema, busca `Radar`. El launcher está en
`/home/paolo/Projects/Radar/scripts/radar-launch.sh` y registra incidencias en:

```bash
tail -f /home/paolo/.local/state/radar/launcher.log
tail -f /home/paolo/.local/state/radar/api.log
tail -f /home/paolo/.local/state/radar/frontend.log
```

La entrada `.desktop` abre Chromium con `--app`, por lo que Radar aparece como una ventana
independiente. Para ejecutarlo manualmente usa `http://127.0.0.1:3000/radar`.

## Verificación y respaldo

Ejecuta `ruff check`, `pytest`, `python -m compileall` y `docker compose ps`. Para respaldo lógico usa `docker exec radar-postgres pg_dump -U radar -d radar > radar-backup.sql`. No borres el volumen para actualizar tablas; crea migraciones incrementales.
