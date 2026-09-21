# Radar

Radar es un sistema personal de Career Intelligence para el mercado inicial de Ingeniería Industrial en Perú.

<img width="1571" height="1390" alt="Capture" src="https://github.com/user-attachments/assets/e76df213-dea0-447b-87e9-3cd2c92851d1" />

## Estado

La V1 implementa la columna vertebral y V2 añade memoria profesional:

```text
buscar → normalizar → clasificar → deduplicar → observar → guardar → puntuar → evolucionar
```

La fuente de verdad es SQLite (archivo local, sin servidor). el agente integrado de la app trabaja sobre esos datos y, de forma opcional, un agente externo se conecta mediante el MCP propio `radar`; las postulaciones automáticas están fuera del alcance. La primera entrega del frontend geográfico ya está disponible en `frontend/`.

El frontend incluye las vistas `Distritos`, `Radar`, `Análisis` y `CVs`. `Análisis` ejecuta consultas
SQL de solo lectura sobre SQLite (con consultas predefinidas) y muestra el resultado como
cifra, barras, serie o tabla. `CVs` toma como objetivos las ofertas con ★, ordena por cercanía a tu perfil real
(calculada por reglas), y ofrece matriz de brechas, comparación en columnas y candidatos ideales
hipotéticos redactados por el agente; no son CVs enviables (ver
[CVs objetivo](docs/target-profiles.md) y [CV en Word (plan)](docs/cv-word-plan.md)).

## Móvil, carreras y agente de chat

- **App móvil (PWA):** `http://127.0.0.1:8100/m`. Pestañas Hoy (ofertas frescas con el motivo del
  encaje y qué skill aprender primero), Seguimiento (guardada → postulé → entrevista → oferta),
  Agente (chat) y Ajustes. Se instala desde el navegador y muestra el último feed sin conexión.
- **Carreras:** la taxonomía, las competencias y los pesos del score viven en
  `src/radar/careers/packs/*.json` (Ingeniería Industrial y Contabilidad). Añadir una carrera es
  añadir un JSON; se elige en Ajustes o con `RADAR_CAREER`.
- **Adaptable a cualquier carrera:** en el primer inicio (escritorio y móvil) unas preguntas fijan tu carrera, dónde buscas (Lima primero, o cualquier ciudad del Perú), tu perfil y tus skills. Si tu carrera no está, la creas indicando áreas con palabras clave y skills; se guarda junto a tu base de datos. "Actualizar mercado ahora" trae las ofertas de tu carrera. Cada persona maneja su propia base local.
- **Agente de chat (opcional, apagado por defecto):** un ingeniero industrial senior (marco ISE BoK) que consulta tus
  datos, cita distritos y ofertas con `@`, conoce tu CV, mantiene la base y, con tu confirmación, cambia perfil, CV,
  temporizador y pesos. En escritorio es una ventana flotante (`Ctrl+J`) o un panel fijado; se activa en Ajustes
  (`/ajustes`) y apagado el servidor rechaza el chat. Es una terminal minimal al estilo de Claude Code: `/` abre los
  comandos (con alias en español), `/help` y otros abren una ventana temporal que se cierra con `Esc`, `Shift+Tab`
  cambia entre modo manual, auto y plan, `/resume` es un selector de conversaciones con búsqueda, `/model` y
  `/effort` comparten un selector, y `?` muestra los atajos. Usa tu propia clave de API (DeepSeek por defecto;
  también OpenAI, OpenRouter, Ollama o un endpoint compatible) con tope mensual de tokens. Recibe el contexto
  explícito de la pantalla (vista, distrito, filtros, oferta abierta), que se puede apagar con `Ctrl+K`. Comparte
  las 58 herramientas del MCP (45 visibles en el chat, `src/radar/tools.py`); las que escriben piden confirmación.
  Guía completa: [docs/agente.md](docs/agente.md).
- **Acceso desde el celular:** ver [Acceso remoto](docs/operations.md#acceso-remoto-desde-el-celular).

Plan y estado: [Radar multicarrera, móvil y agente](docs/plan-multicarrera-movil.md).

## Documentación

- [Guía para agentes](AGENTS.md)
- [Arquitectura y flujo](docs/architecture.md)
- [Modelo de datos](docs/database.md)
- [MCP opcional para agentes externos](docs/mcp.md)
- [Operación diaria](docs/operations.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Seguridad y cumplimiento](docs/security.md)
- [Roadmap V2/V3](docs/roadmap.md)
- [Plan general](docs/plan-general.md)
- [Plan de rendimiento](docs/plan-rendimiento.md)
- [Agente de Radar: identidad, herramientas, modos e interfaz](docs/agente.md)
- [Plan multicarrera, móvil y agente](docs/plan-multicarrera-movil.md)
- [Plan de escritorio y agente como ventana](docs/plan-escritorio.md)
- [Dirección de producto](docs/product-direction.md)
- [CVs objetivo](docs/target-profiles.md)
- [CV en Word: viabilidad y plan](docs/cv-word-plan.md)

## Arranque

```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

No se necesita ningún servicio externo: SQLite se crea automáticamente en
`~/.local/share/radar/radar.db` (o en `RADAR_DB_PATH`).

Para Computrabajo, el adaptador usa `npx mcp-computrabajo@latest` en modo stdio. La búsqueda no requiere cookie según el servidor; no se configuran cookies ni herramientas de perfil/postulación en Radar.

```bash
radar ingest --source computrabajo --query "practicante de procesos" --location Lima --limit 10
```

El perfil se modifica únicamente mediante una acción explícita local:

```bash
radar profile --name "Paolo" --area "Procesos" --area "Data / BI" --location Lima --skill Excel=advanced --skill SQL=intermediate
```

Los avances se conservan como eventos, sin borrar versiones anteriores:

```bash
radar career-event --type course --title "Curso de PostgreSQL" --started-on 2026-09-11
```

Para JobSpy, usa el entorno separado de Python 3.12 porque la versión actual fija NumPy 1.26.3:

```bash
uv pip install --python .venv-jobspy/bin/python -e '.[jobspy]'
.venv-jobspy/bin/radar ingest --source jobspy --query "practicante ingeniería industrial" --location Lima --limit 10
```

Opcional: para conectar un agente externo (Claude Code, Antigravity, Hermes u otro cliente MCP; ver [docs/mcp.md](docs/mcp.md)):

```json
{
  "mcpServers": {
    "radar": {
      "command": "/home/paolo/Projects/Radar/.venv/bin/radar-mcp"
    }
  }
}
```

Para abrir el frontend geográfico manualmente en desarrollo, inicia la API y luego Next.js en terminales separadas:

```bash
.venv/bin/radar-api
cd frontend && npm run dev
```

Visita `http://localhost:3000/radar`. La API HTTP escucha en `http://127.0.0.1:8100`; además de consultas de lectura permite actualizar el estado personal visible/oculta de una oferta consultar `/api/skills/overview`, ejecutar consultas de solo lectura en `/api/analytics/query` y leer los CVs objetivo en `/api/cv/*`. El MCP mantiene su transporte stdio independiente.

También puedes abrir Radar desde el launcher de aplicaciones del sistema. El acceso ejecuta
`scripts/radar-launch.sh`, compila `frontend/out` si hace falta, inicia la API si no está activa y abre
FastAPI como aplicación independiente de Chromium (`--app`) con un perfil separado en
`~/.local/state/radar/chromium`. La API permanece activa aunque se cierre la ventana para que una
ventana reutilizada no quede sin backend.

### Frontend geográfico

La vista `/radar` ofrece búsqueda, filtros por área/seniority/modalidad/salario/frescura,
lista de ofertas, detalle, ranking por distrito y dos modos de visualización:

- `Distritos`: coropleta de Lima/Callao con cantidad de ofertas y selección sincronizada.
- `Radar`: selector de distrito como centro fijo, zoom automático, radios concéntricos
  seleccionables de 2, 5 y 10 km y distancia geográfica calculada con Haversine. El filtro se
  refleja simultáneamente en contador/lista/mapa; el radio activo y el centro permanecen anclados
  al mapa y respetan `prefers-reduced-motion`.

Las coordenadas se infieren de forma aproximada desde distrito o ciudad y se informa esa
limitación en la interfaz. MapLibre es el motor principal; si el navegador no soporta
WebGL2, se activa automáticamente un fallback con Leaflet. La interfaz usa un tema grafito
oscuro y el explorador tiene scroll propio para ventanas pequeñas.

Herramientas MCP disponibles: `ingest_jobs`, `search_saved_jobs`, `get_market_summary`, `get_user_profile`, `list_recommended_jobs`, `get_job_history`, `get_career_timeline`, `record_career_event`, `capture_market_history`, `get_market_history`, `track_job_application`, `list_job_applications`, `get_target_context`, `save_target_profile`, `get_target_matrix`, `resolve_nearest_districts` y `health`. El detalle está en [MCP de Radar](docs/mcp.md).

Para sumar LinkedIn, Bumeran, Laborum o Empleos Perú sin automatizar cuentas personales, importa un CSV/JSON preparado por ti:

```bash
.venv/bin/radar import-jobs --source linkedin --file ofertas.csv
```

El CSV puede incluir `published_at`, `work_mode`, `hours_per_week`, `schedule_text`, `salary_min`, `salary_max`, `salary_currency`, `salary_period`, `application_status` y `application_checked_at`. La vista de Radar se puede consultar por área (`area`) y ordena por fecha y actualización; el agrupamiento por área se obtiene desde `job_areas`.

Las búsquedas automáticas y la vista web usan por defecto ofertas publicadas en los últimos 7 días; puedes cambiar la antigüedad a 14, 30 o 90 días desde la interfaz. Las ofertas antiguas no se borran: quedan en SQLite como historial, pero no aparecen cuando están fuera de la ventana elegida.

La vista web se basa en la antigüedad de `published_at` y no excluye ofertas por `is_active`, estado de aplicación ni una regla especial de LinkedIn. Las ofertas ocultadas manualmente se excluyen de la vista normal y pueden consultarse/restaurarse desde el ícono de ojo. La URL original se conserva y el popup identifica la plataforma por su dominio cuando es posible. El detalle usa una tarjeta compacta: la descripción se resume inicialmente y se puede expandir con `Ver descripción completa`, evitando scrollbars anidados tanto en ofertas como en señales del Radar.

La ingesta conserva el mercado capturado aunque una oferta no publique salario. La taxonomía de `src/radar/taxonomy.py` asigna una relevancia trazable: `core` para áreas centrales de Ingeniería Industrial, `adjacent` para áreas útiles relacionadas y `out_of_focus` para señales comerciales o no pertinentes. El salario se usa como métrica y filtro posterior, no para descartar ofertas durante la captura.

La interfaz mantiene una composición sin barra superior: `Radar` funciona como título principal
del explorador, dejando todo el alto disponible para filtros, ofertas y mapa.

El estado personal se guarda en `job_user_status`, separado de `jobs`. Ocultar una oferta requiere
un motivo (`closed`, `not_interested`, `applied`, `duplicate` u `other`) y no elimina la oferta
canónica. Actualmente aplica a la instalación local completa; todavía no existe soporte multiusuario.
Las ofertas favoritas se guardan en `job_user_favorites` y se consultan desde la vista Favoritos
mediante la estrella `☆`/`★`.

Para mantener el mercado actualizado en segundo plano, Radar tiene un temporizador de usuario que ejecuta dieciséis consultas amplias de áreas industriales en Indeed, LinkedIn (búsqueda pública vía JobSpy, sin login) y Computrabajo **cada 7 días**, con una ventana de 10 días para solapar las corridas. Computrabajo se puede pausar con `RADAR_COMPUTRABAJO_ENABLED=0`. Desde el agente puedes cambiar la frecuencia (`set_refresh_schedule`) o traer ofertas de un distrito (`refresh_market`). La ingesta no filtra por salario; el sueldo se utiliza después como dato de análisis y filtro opcional:

```bash
systemctl --user status radar-refresh.timer
tail -f /home/paolo/.local/state/radar/refresh.log
```

El refresco usa JobSpy (Indeed y LinkedIn) y el adaptador MCP de Computrabajo; Bumeran, Laborum y Empleos Perú continúan entrando mediante importación asistida para no automatizar cuentas personales.

## Límites deliberados

- Las coordenadas todavía no se persisten en SQL; siguen siendo inferidas en la API.
- El score se calcula con reglas trazables; el LLM no decide el número.
- Se conserva el `raw_payload` de cada fuente.
- Los duplicados se detectan por fingerprint y no se borran automáticamente.
- No se automatizan postulaciones, mensajes ni cambios del perfil.
