# Operación de Radar

## Instalación

```bash
cd /home/paolo/Projects/Radar
cp .env.example .env
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

No se necesita ningún servicio externo: SQLite se crea automáticamente en
`~/.local/share/radar/radar.db` (o en `RADAR_DB_PATH`) la primera vez que corre `radar` o `radar-api`.

## Ingesta

Computrabajo:

```bash
.venv/bin/radar ingest --source computrabajo --query "practicante de procesos" --location Lima --limit 10
```

La búsqueda consulta primero las tarjetas y luego `get-job-detail` para enriquecer cada oferta con descripción, salario, contrato y jornada. El enriquecimiento se puede desactivar para una prueba rápida con `RADAR_COMPUTRABAJO_DETAILS=0`; un fallo en el detalle conserva la tarjeta resumida y no interrumpe el lote.

El adaptador acepta las fechas ISO y las etiquetas relativas que entrega el portal, como
`Hace 1 hora`, `Hace 2 días`, `Hoy` y `Ayer`, para que la ventana de frescura no descarte
ofertas recientes por falta de fecha interpretable.

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

En LinkedIn puedes conservar `application_status` y `application_checked_at` como evidencia de la importación, pero la vista web se basa en la antigüedad de `published_at` y no aplica una exclusión especial por fuente. Si cambia el anuncio, vuelve a importar la misma fila para actualizar sus datos; no se borra el registro histórico.

Ejemplo mínimo verificable:

```text
Practicante de Sistemas,Empresa,https://www.linkedin.com/jobs/view/123,Lima,"SQL Server y soporte",remote,,,,,open,2026-09-11T17:00:00-05:00
```

## Frescura de las ofertas

Las búsquedas automáticas usan por defecto un máximo de 14 días desde `published_at`:

```bash
.venv/bin/radar ingest --source computrabajo --query "automatización procesos" --location Lima --max-age-days 14
```

Para una revisión diaria más estricta, usa `--max-age-days 7`. Las ofertas sin fecha, futuras o fuera del rango no se muestran como recomendación. No se eliminan de SQLite: permanecen disponibles para historial y análisis de mercado.

Para reparar ofertas capturadas antes de la inferencia de modalidad y sector:

```bash
.venv/bin/radar repair-data
```

Para desactivar ofertas que ninguna fuente volvió a ver en N días (por defecto 45, evita que la tabla crezca sin límite aunque la vista ya las oculte por fecha):

```bash
.venv/bin/radar expire-stale --days 45
```

Para visitar las URLs de ofertas activas y detectar cierres reales (404/410 se marcan `closed`; bloqueos anti-bot 401/403 quedan en `unknown`, nunca se asumen como cierre):

```bash
.venv/bin/radar check-applications --limit 150 --recheck-after-days 3
```

Computrabajo e Indeed bloquean este chequeo casi siempre (anti-bot), así que en la práctica solo detecta cierres de forma confiable en LinkedIn.

## Refresco continuo

El refresco persistente se ejecuta como servicio de usuario **cada 7 días** (`radar-refresh.timer`; también 5 minutos después de cada arranque). Consulta dieciséis búsquedas amplias de datos/BI, procesos, automatización, transformación digital, ERP, planeamiento, supply chain, logística, compras, producción, calidad, mantenimiento, control de gestión y PMO en Indeed, LinkedIn (vía `python-jobspy`, sin login) y Computrabajo (vía MCP, con detalle completo por oferta). Cada portal corre de forma aislada y un fallo no bloquea el otro; el script registra qué paso falló en el resumen final del log en vez de tragarse el error en silencio. La ingesta no filtra por salario: captura el mercado y deja el sueldo para análisis posterior. El script usa 10 días por defecto (`--max-age-days`), de modo que las corridas semanales se solapen y no se pierdan ofertas publicadas entre una y otra; puedes cambiarlo con `RADAR_MAX_AGE_DAYS`. Tras ingerir, corre `repair-data`, `expire-stale` y `check-applications` antes de guardar el snapshot del mercado.

```bash
systemctl --user status radar-refresh.timer
systemctl --user list-timers radar-refresh.timer
tail -f /home/paolo/.local/state/radar/refresh.log
```

El servicio es tolerante a fallos por consulta, usa un máximo de 10 días por defecto y guarda snapshots del mercado. Una oferta pasada desaparece de la vista accionable por el filtro de fecha; si además ninguna fuente la vuelve a ver en 45 días, `expire-stale` la desactiva mientras el registro histórico permanece en SQLite. Para detenerlo temporalmente: `systemctl --user disable --now radar-refresh.timer`; para reactivarlo: `systemctl --user enable --now radar-refresh.timer`.

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
independiente. El launcher verifica `frontend/out`, inicia la API si hace falta y abre la aplicación
estática servida por FastAPI en `http://127.0.0.1:8100/radar`. `radar-api` permanece activo al cerrar
la ventana para soportar la reutilización del perfil de Chromium.

### Ocultar y restaurar ofertas

Desde el detalle de una oferta visible, selecciona `Ocultar oferta` y elige un motivo:
`Ya cerró`, `No me interesa`, `Ya postulé`, `Oferta duplicada` u `Otro`. La oferta se registra
en `job_user_status` y deja de aparecer en la vista normal. El ícono de ojo junto a `Ofertas
recientes` abre la lista de ofertas ocultas; desde el detalle se puede seleccionar `Restaurar
oferta` para volver a incluirla.

Este flujo no elimina ni modifica la fila de `jobs`. Actualmente el estado es local a la instalación
de Radar y no hay separación por cuentas de usuario.

## Verificación y respaldo

Ejecuta `ruff check`, `pytest` y `python -m compileall`. Para respaldo lógico, copia el archivo SQLite
con la base cerrada o usa el comando `.backup` de `sqlite3`:

```bash
sqlite3 ~/.local/share/radar/radar.db ".backup '/home/paolo/Projects/Radar/backups/radar-$(date +%F).db'"
```

No edites el esquema SQLite a mano; los cambios van en
[`src/radar/db/schema_sqlite.sql`](../src/radar/db/schema_sqlite.sql), ver
[`docs/database.md`](database.md).

## Reiniciar la API tras cambios de backend

`scripts/radar-launch.sh` reinicia la API automáticamente si algún `.py` de `src/radar/` es más nuevo
que el proceso en marcha, así que abrir Radar desde el launcher basta. Si la API se inició por otro
medio, o para reiniciarla a mano, las rutas nuevas devuelven 404 hasta hacerlo:

```bash
pkill -f ".venv/bin/radar-api"
nohup .venv/bin/radar-api >>~/.local/state/radar/api.log 2>&1 &
```

Los servidores MCP (si usas uno externo) también deben recargarse para ver herramientas nuevas.

## CVs objetivo: datos locales

Los archivos de la vista `CVs` están en `~/.local/share/radar/` (o junto a `RADAR_DB_PATH`):
`cv_master.json` (perfil real), `targets/*.json` (un candidato ideal por oferta) y `photo.jpg`. No están
en Git. Las herramientas MCP `save_target_profile` y `get_target_context` los crean y leen; incluir
la carpeta en los respaldos junto a `radar.db`.


## Acceso remoto desde el celular

Radar es local: el celular necesita llegar a tu PC, que debe estar encendida.

1. Instala Tailscale en la PC y en el teléfono (o usa un túnel de Cloudflare).
2. Define una clave de acceso larga y publica la API solo en la interfaz privada:

   ```bash
   export RADAR_ACCESS_TOKEN='una-clave-larga-y-unica'
   RADAR_API_HOST=<ip-tailscale-de-la-pc> .venv/bin/radar-api
   ```

3. Abre `http://<ip-tailscale>:8100/m` en el teléfono e instálala ("Añadir a pantalla de inicio").
   La cookie de sesión solo se marca `Secure` bajo HTTPS; con `tailscale serve` obtienes HTTPS.

Sin `RADAR_ACCESS_TOKEN` no hay autenticación: no expongas la API fuera de `127.0.0.1` así. Nunca
uses `0.0.0.0` en una red que no controles.

## Agente de chat

Ajustes → Agente: elige proveedor, modelo y pega tu clave. La clave se guarda en
`~/.local/share/radar/secrets.json` (permisos `0600`), nunca en la base de datos ni en el navegador.
El consumo se cuenta en la tabla `agent_usage` y el chat se detiene al llegar al tope mensual.

En el chat de escritorio, `/model` y `/effort` abren el mismo selector en línea: `↑`/`↓` eligen el modelo, `←`/`→`
cambian el esfuerzo (`auto`, `none`, `low`, `high`, `max`), `Enter` aplica ambos y `Esc` cierra. El selector separa
el nombre visible del ID que se envía al proveedor: en DeepSeek muestra `DeepSeek V4.1 Flash` (`deepseek-flash`) y
`DeepSeek V4 Pro` (`deepseek-v4-pro`). También puedes aplicar directamente `/model deepseek-flash` o `/effort high`.

Los dos modelos DeepSeek visibles son los identificadores oficiales actuales. `deepseek-v4-flash` es
un alias legado y no se muestra en el selector normal; si se conserva en una base antigua, aparece
solo como modelo actual para no cambiar silenciosamente la configuración existente. El modelo
`deepseek-flash` corresponde actualmente a DeepSeek-V4.1-Flash.

La interfaz, los atajos, los modos (manual, auto y plan) y el resto de capacidades del agente están descritos en
[agente.md](agente.md). Tras cambios de backend hay que reiniciar la API (ver «Reiniciar la API tras cambios de backend»).

### Contexto de pantalla y comparaciones

El agente recibe en cada mensaje el contexto de la interfaz actual. Incluye la vista abierta
(`Mapa`, `Análisis` o `CVs`), el modo del mapa, distrito y radio seleccionados, filtros activos,
oferta seleccionada, cantidad visible y, en `Análisis`, las ventanas restauradas o recién creadas.
El contexto se actualiza al cambiar de vista o al generar un análisis; por eso una respuesta
posterior puede reflejar una ventana nueva sin tratar el estado anterior como un error inventado.

`Ctrl+K` decide cuánto de ese contexto se envía: apagado, selección (por defecto, sin SQL ni filas de análisis) o
completo. Con un distrito seleccionado el agente recibe su conteo propio (`districtJobs`), no el total visible.
Las menciones con `@` (distritos, ciudades y ofertas) viajan siempre como una lista explícita.

Para comparar el lugar seleccionado con otro, formula la petición directamente, por ejemplo:
`compara lo que tengo seleccionado con Lurín`. El agente usa `compare_places`, una consulta de solo lectura que
compara ofertas, áreas, empresas, modalidad, seniority, salario mediano y, como una dimensión más, las señales de
producción. `get_place_profile` da la radiografía de un solo lugar. La ubicación se interpreta de forma aproximada
según el texto y la geolocalización de Radar; no representa sedes exactas.

## Mantenimiento de datos

- **Clasificación:** el agente puede auditar (`audit_classification`, solo lectura) si las áreas y la relevancia
  guardadas coinciden con las reglas vigentes, y reclasificar (`reclassify_jobs`, con confirmación). Cada
  reclasificación guarda un JSON reversible (`reclassify-<fecha>.json`) junto a la base de datos y registra la huella de
  las reglas; si las reglas cambian después, el prompt del agente avisa que conviene volver a auditar. Detalle en
  [database.md](database.md#clasificación-profesional).
- **Respaldos:** `run_maintenance(task="backup")` usa la API de respaldo de SQLite y guarda las últimas 5 copias en
  `backups/` junto a la base de datos. Conviene hacer uno antes de reclasificar o de reparar datos.
- **Otras tareas:** `repair_data`, `expire_stale` (desactiva, no borra), `check_applications` (visita hasta 60 enlaces) y
  `market_snapshot`. Los mismos comandos siguen disponibles por terminal (`radar repair-data`, `radar audit-data`,
  `radar expire-stale`, `radar check-applications`, `radar market-snapshot`).
- **CV:** `update_cv` guarda `cv_master.json.bak-<fecha>` (últimas 5) antes de cada cambio.
- **Estado:** `get_system_status` resume base de datos, integridad, ofertas por tier, última captura y temporizador.

## Cobertura nacional

`scripts/radar-refresh.sh` captura Lima por defecto. La cobertura adicional se habilita explícitamente
con `RADAR_CITIES`, una lista separada por comas (por ejemplo, `RADAR_CITIES="Arequipa,Trujillo"`),
con 4 consultas por ciudad en JobSpy y Computrabajo. `RADAR_CITIES=""` mantiene el refresco en solo Lima;
cada ciudad añade varios minutos al refresco. Una ciudad nueva también debe existir en
`src/radar/geolocation.py` (`_CITIES`) para aparecer en el mapa.


## Captura automática y por lugar

- **Automática:** cada 7 días (`OnUnitActiveSec=7d`, más 5 minutos tras cada arranque). El agente puede cambiar la
  frecuencia con `set_refresh_schedule(days, on_boot)` (de 1 a 30 días; 0 desactiva el temporizador; `on_boot=false` quita
  el disparo tras el arranque) y consultar cuándo corrió y cuándo corre con `get_system_status`. A mano: edita
  `~/.config/systemd/user/radar-refresh.timer`, luego `systemctl --user daemon-reload` y
  `systemctl --user restart radar-refresh.timer`. Solo funciona en Linux con systemd.
- **Por lugar (agente y MCP):** `refresh_market(place, limit)` pide confirmación y trae ofertas enfocadas en un distrito o
  ciudad en segundo plano (varios minutos); `get_refresh_status()` informa el avance. Las fuentes buscan por ciudad: en JobSpy
  la ubicación es «Distrito, Lima» y en Computrabajo el distrito se añade a la palabra clave, así que el resultado se sesga
  hacia el lugar sin limitarse a él.
