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

El refresco persistente se ejecuta como servicio de usuario una vez al día. Consulta dieciséis búsquedas amplias de datos/BI, procesos, automatización, transformación digital, ERP, planeamiento, supply chain, logística, compras, producción, calidad, mantenimiento, control de gestión y PMO en Indeed, LinkedIn (vía `python-jobspy`, sin login) y Computrabajo (vía MCP, con detalle completo por oferta). Cada portal corre de forma aislada y un fallo no bloquea el otro; el script registra qué paso falló en el resumen final del log en vez de tragarse el error en silencio. La ingesta no filtra por salario: captura el mercado y deja el sueldo para análisis posterior. El servicio usa 7 días por defecto para mantener la vista accionable; puedes ampliar el rango temporalmente con `RADAR_MAX_AGE_DAYS=14`. Tras ingerir, corre `repair-data`, `expire-stale` y `check-applications` antes de guardar el snapshot del mercado.

```bash
systemctl --user status radar-refresh.timer
systemctl --user list-timers radar-refresh.timer
tail -f /home/paolo/.local/state/radar/refresh.log
```

El servicio es tolerante a fallos por consulta, usa un máximo de 7 días por defecto y guarda snapshots del mercado. Una oferta pasada desaparece de la vista accionable por el filtro de fecha; si además ninguna fuente la vuelve a ver en 45 días, `expire-stale` la desactiva mientras el registro histórico permanece en SQLite. Para detenerlo temporalmente: `systemctl --user disable --now radar-refresh.timer`; para reactivarlo: `systemctl --user enable --now radar-refresh.timer`.

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

Los servidores MCP (Antigravity, Claude Code, Hermes u otro cliente) también deben recargarse para ver herramientas nuevas.

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

## Cobertura nacional

`scripts/radar-refresh.sh` captura Lima y, además, las ciudades de `RADAR_CITIES` (por defecto Arequipa,
Trujillo, Chiclayo, Piura, Cusco, Huancayo, Iquitos, Tacna, Cajamarca e Ica) con 4 consultas cada una,
en JobSpy y Computrabajo. Amplía o reduce la lista con la variable (`RADAR_CITIES=""` = solo Lima);
cada ciudad añade varios minutos al refresco. Una ciudad nueva también debe existir en
`src/radar/geolocation.py` (`_CITIES`) para aparecer en el mapa.
