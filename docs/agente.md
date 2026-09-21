# Agente de Radar

Guía de referencia del agente de chat: qué es, cómo se comporta, qué puede hacer, cómo se usa la
interfaz y qué límites tiene. El agente comparte herramientas con el servidor MCP (`src/radar/tools.py`),
así que todo lo que hace en la app también lo puede hacer un agente externo (opcional, vía MCP) con el mismo registro.

## Identidad («alma»)

El prompt de sistema tiene dos partes: las reglas operativas (`SYSTEM_PROMPT` en `src/radar/agent/loop.py`) y
el carácter (`src/radar/agent/soul.md`). El alma define a un ingeniero industrial y de sistemas senior con el
marco del **ISE Body of Knowledge (IISE, 2026)** y criterio del mercado peruano: mentor directo, realista,
visionario e independiente, cuya lealtad es con los datos y con el futuro de la persona, no con darle la razón.

- Usa las 14 áreas del BoK con el nombre que tienen en Radar (más «Otras» y «Ventas / Comercial», fuera de foco).
- Distingue dato (herramienta) de inferencia o proyección, y dice qué tan seguro está.
- Al comparar, declara siempre el criterio (volumen, mediana salarial, modalidad, seniority, mezcla de áreas).
- Un saludo se responde sin llamar herramientas; no ejecuta `get_setup_status` ni `get_today_feed` por su cuenta.
- Conoce a la persona: su nombre y el titular de su CV van en el prompt, y `get_my_cv` da la trayectoria completa.
- Si el prompt detecta que las reglas de clasificación cambiaron desde la última reclasificación, añade un aviso
  para que audite (`audit_classification`) y proponga `reclassify_jobs`.

Cualquier cambio de personalidad se hace en `soul.md` (se empaqueta con el paquete `radar`).

## Herramientas (58 en total, 45 en el chat)

`src/radar/tools.py` es el único registro. Cada herramienta declara `write` (pide confirmación) y `chat`
(visible para el agente de la app). Las marcadas **MCP** solo están en el servidor MCP.

| Grupo | Herramientas |
|---|---|
| Mercado y ofertas | `search_saved_jobs` (filtros por área, sector, exclusión de sectores y texto), `get_today_feed`, `find_jobs_near`, `get_job_details`, `explain_job_fit`, `compare_jobs`, `get_skill_demand`, `get_market_breakdown` (por área, lugar, empresa, modalidad, seniority, sector o portal, con filtros), `get_place_profile`, `compare_places`, `get_salary_stats`, `plan_learning`, `get_market_history`, `get_data_schema`, `run_readonly_sql`; **MCP:** `get_market_summary`, `list_recommended_jobs`, `get_skill_impact`, `get_job_history`, `health` |
| Perfil, CV y memoria | `get_my_profile`, `update_profile_fields`\*, `get_user_profile`, `get_my_cv`, `update_cv`\*, `get_user_memory`, `remember_user`\*, `search_past_conversations`, `get_career_timeline`, `record_career_event`\*, `list_career_tracks`, `set_career_track`\*, `create_career_pack`\* |
| Plan de cierre y CV descargable | `get_closure_plan`, `close_gap`\*, `preview_cv`, `build_cv`\* |
| Seguimiento | `favorite_job`\*, `track_job_application`\*, `list_job_applications` |
| Captura y sistema | `refresh_market`\*, `get_refresh_status`, `get_system_status`, `set_refresh_schedule`\*, `run_maintenance`\*, `set_score_weights`\*, `audit_classification`, `reclassify_jobs`\*, `get_setup_status`, `get_help`; **MCP:** `ingest_jobs`\*, `capture_market_history`\* |
| CVs objetivo (**MCP**) | `get_target_context`, `list_targets`, `save_target_profile`\*, `get_target_matrix`, `resolve_nearest_districts` |

\* Escribe: en el chat aparece una tarjeta y solo se ejecuta si la persona la aprueba.

Decisiones de diseño:

- **Vía más corta:** el prompt ordena usar primero las herramientas directas; `run_readonly_sql` es el último recurso,
  con 2 intentos, y sus errores traen el esquema para no gastar un paso en `get_data_schema`.
- **Sin límites que rompan la respuesta:** un turno tiene hasta 8 pasos. En el último se le quitan las herramientas y
  se le pide cerrar con lo obtenido. Una consulta idéntica repetida se corta. Los resultados grandes se recortan
  por elementos (JSON siempre válido) y los de turnos anteriores solo conservan un extracto.
- **Herramientas ligeras:** `search_saved_jobs` devuelve un extracto de la descripción (la ficha completa está en
  `get_job_details`).
- **Lo que el agente no puede cambiar:** la clave de API, el modo solo lectura y el tope de tokens los cambia la
  persona en Ajustes. Tampoco postula ni envía mensajes.

## Modos

`Shift+Tab` recorre tres modos, visibles en el pie de la ventana (no escriben nada en el chat):

| Modo | Comportamiento |
|---|---|
| `manual mode on` | Cada acción que cambia datos pide confirmación. |
| `auto mode on` | Aprueba solas las acciones de seguimiento personal (`favorite_job`, `track_job_application`, `remember_user`, `record_career_event`). Las de sistema, CV, perfil, pesos, captura y reclasificación siguen pidiendo confirmación. |
| `plan mode on` | El servidor no ofrece herramientas de escritura y rechaza cualquier llamada. El agente investiga y termina con un plan numerado; una tarjeta permite aprobarlo (`1`) o seguir planificando (`2`). Al aprobar, sale del modo plan y ejecuta paso a paso. |

`/plan [objetivo]` activa el modo plan (con un objetivo lo envía de una vez); `/plan off` sale. El ajuste
persistente **solo lectura** (`/readonly`, Ajustes) quita las herramientas de escritura siempre y se muestra
aparte en el pie (`· read-only`).

## Interfaz

Ventana flotante (`Ctrl+J`) o panel fijado a la derecha en escritorio; pestaña Agente en el móvil. Estética de
terminal (texto de 12 px en escritorio, esquinas rectas, sin barras de desplazamiento visibles, colores al estilo
de Claude Code). Con la conversación vacía muestra un banner con la marca, la versión, el modelo, la carrera y las
ofertas activas. La barra superior muestra el título de la conversación (clic o `/rename` para cambiarlo).

### Atajos

| Tecla | Acción |
|---|---|
| `Enter` / `Shift+Enter` | Enviar / nueva línea (también `\` + Enter) |
| `/` · `Tab` · `↑↓` | Comandos, autocompletar y elegir |
| `@` | Citar un distrito, ciudad u oferta; `Tab` o `Enter` elige. El mensaje lleva la lista explícita de menciones |
| `↑` (vacío) / `Ctrl+R` | Recuperar / buscar mensajes anteriores |
| `Esc` / `Esc Esc` | Detener la respuesta / volver a tu último mensaje para editarlo |
| `Shift+Tab` | Modo: manual → auto → plan |
| `Ctrl+K` | Contexto de pantalla: apagado → selección → completo |
| `Ctrl+O` | Mostrar u ocultar el resultado completo de las herramientas |
| `Ctrl+C` | Detener; con el campo vacío, dos veces cierra |
| `PgUp` / `PgDn` | Recorrer la conversación |
| `1` `2` `3` | Aprobar / aprobar siempre (sesión) / rechazar (`y` y `n` también) |
| `#` texto | Guardar en memoria |
| `?` (vacío) | Ventana de atajos |

### Comandos

Los nombres son los de Claude Code, con alias en español. Los informativos abren una **ventana temporal** (se cierra
con `Esc`, no entra en la conversación): `/help`, `/keys`, `/status`, `/doctor`, `/tools`, `/context`, `/cost`,
`/profile`. Otros muestran un **aviso breve**: `/copy`, `/export`, `/pin`, `/readonly`, `/refresh`, y `/model` o
`/effort` con argumento. `/today`, `/map`, `/pipeline`, `/skills`, `/compact` y `/memory` responden en el chat.
`/model`, `/effort` y `/resume` abren selectores: `/model` y `/effort` comparten uno (`↑↓` modelo, `←→` effort);
`/resume` lista las conversaciones (escribe para filtrar por título o contenido, `Enter` abre, `Ctrl+D` borra con
confirmación). `/plan` es el modo plan y `/learn` el plan de aprendizaje. `/delete todo` pide confirmar con
`/delete todo confirmar`. Los que piden algo al modelo son `/init`, `/explain`, `/learn` y `/summary`.

### Contexto de pantalla

El agente recibe la vista, el modo del mapa, el distrito o radio, los filtros, la oferta abierta y el conteo del
distrito (`districtJobs`, distinto del total visible). `Ctrl+K` elige cuánto enviar: **apagado** (nada),
**selección** (por defecto: sin SQL ni filas de análisis) o **completo** (con filas de análisis). El agente lo usa en
silencio, sin citarlo. Las menciones con `@` viajan siempre y tienen prioridad.

## Memoria y conversaciones

- **Memoria durable** (`agent_memories`, con búsqueda de texto): preferencias, metas y decisiones **confirmadas**.
  Se guarda con `remember_user` (tarjeta de confirmación) o con `# texto`. Las 30 notas más recientes van en el
  prompt; el resto se busca con `get_user_memory`. No guarda secretos ni conversaciones completas.
- **Conversaciones** (`conversations`): se guardan en la base local y se reanudan con `/resume`. El agente puede
  buscar en ellas con `search_past_conversations` (sin distinguir tildes; devuelve fragmentos, no conversaciones
  enteras) y solo cuando la persona alude a algo hablado antes; no se cargan en cada mensaje.

## CV por texto

`update_cv(section, action, item, match)` edita `cv_master.json`, la misma fuente que lee la vista de CVs. Secciones:
`certifications`, `experience`, `education`, `languages`, `projects`, `contact` (email, teléfono, LinkedIn, ubicación), `gaps` (brechas de evidencia), `summary` y `headline`.
Acciones: `add`, `update`, `remove`. Valida los campos permitidos y las fechas `AAAA-MM`, rechaza duplicados y
coincidencias ambiguas, conserva las claves que no toca, guarda `cv_master.json.bak-<fecha>` (últimas 5) y escribe de
forma atómica. Solo con lo que la persona dicta. Las skills y herramientas se cambian con `update_profile_fields` (o en Ajustes → Perfil), y la vista
de CVs se ve actualizada al reabrirla.

## Mantenimiento y sistema

- `get_system_status`: BD (tamaño, integridad, respaldos), ofertas por tier, última captura, temporizador,
  reglas de clasificación al día o no, y estado del agente (sin claves).
- `run_maintenance(task)`: lista cerrada: `backup` (API de respaldo de SQLite en `backups/`, conserva 5),
  `repair_data`, `expire_stale` (desactiva, no borra), `check_applications` (hasta 60 enlaces) y `market_snapshot`.
- `set_refresh_schedule(days, on_boot)`: edita `radar-refresh.timer` (1 a 30 días; 0 lo desactiva).
- `set_score_weights`: pesos del puntaje (`area`, `skills`, `seniority`, `education`, `location`, `preference`).
- `audit_classification` / `reclassify_jobs`: ver [Clasificación](database.md#clasificación-profesional).
- `refresh_market(place, limit)` y `get_refresh_status`: captura enfocada en un distrito o ciudad, en segundo plano.
  Las fuentes buscan por ciudad, así que el distrito sesga el resultado sin limitarlo.

Todo lo que escribe pide confirmación, nunca borra ofertas y, cuando aplica, deja una copia reversible.

## Configuración

Ajustes → Agente: proveedor, modelo, esfuerzo de razonamiento, clave (`secrets.json`, `0600`), tope mensual de
tokens, ventana de contexto y solo lectura. El agente nace apagado; apagado, el servidor rechaza el chat. El
consumo se cuenta en `agent_usage`.

## Cómo extenderlo

- **Herramienta nueva:** una función en `src/radar/tools.py` con `@tool(write=..., chat=...)`; aparece en el MCP y en
  el chat. Regenera la skill (`radar skill export --out docs/skills`) y añade una prueba en `tests/test_tools.py`.
- **Comando nuevo:** una entrada en `COMMANDS` de `frontend/components/agent/commands.ts` (y en `VIEWS` si debe abrir
  ventana o aviso).
- **Personalidad o reglas:** `soul.md` y `SYSTEM_PROMPT`; actualiza `help.md` si cambia algo visible.

## Plan de cierre y cierre del ciclo

- `get_closure_plan` responde «qué aprendo o demuestro primero». Toma tus objetivos (ofertas con ★), simula cubrir cada
  skill abierta y suma los puntos de cercanía que ganaría cada puesto; después cruza con el % de ofertas de los últimos
  30 días que la piden. Lo estructural (años de experiencia, grado) va aparte: un curso no lo cierra.
- `close_gap(skill, kind, name, ...)` registra evidencia que la persona ya tiene: un `certificado` (su nombre debe
  mencionar la skill) o un `proyecto` (con descripción de lo que hizo). La guarda en el CV real, retira la nota de brecha
  equivalente, la anota en la línea de tiempo y devuelve la cercanía de cada objetivo antes y después. Si no cambia nada,
  lo dice y explica por qué. Nunca inventa: solo con lo que la persona aporta.
- La vista `CVs` tiene una pestaña **Plan** con el mismo cálculo (`GET /api/cv/plan`), que se recalcula al abrirla.

## CV descargable

`preview_cv(job_id)` y `build_cv(job_id)` producen tu CV **real** para una oferta (no el hipotético). Radar solo
**elige y ordena** lo que ya está en `cv_master.json`; no reformula ni inventa. Detalle y decisiones en
[cv-word-plan.md](cv-word-plan.md). La vista `CVs` lo ofrece dentro del detalle de cada objetivo.

## Perfil editable (Ajustes y agente)

La pestaña **Perfil** de Ajustes y el agente editan el mismo perfil con la misma lógica (`src/radar/profile_edit.py`).
Cada dato tiene un solo dueño y quien edita no tiene que saberlo:

| Dato | Se guarda en |
|---|---|
| Nombre, titular, resumen, distrito de casa, contacto | `cv_master.json` (con copia previa) |
| Formación en una línea, áreas objetivo, lugares, modalidades, skills | SQLite `user_profile` / `user_skills` |

- **Edición parcial.** `update_profile_fields` (y `PATCH /api/me`) solo tocan los campos indicados; nunca borran lo que
  no se menciona. Las listas admiten `*_add` y `*_remove` para agregar o quitar elementos sueltos, y las skills
  `{skill: nivel | remove}`. Todo se valida antes de escribir y, si falla la base, el archivo vuelve a como estaba.
- **Antes → después.** La tarjeta de confirmación del chat muestra el cambio exacto; en Ajustes cada guardado ofrece
  «Deshacer» (la respuesta incluye el `undo` listo para reenviar).
- **Sin duplicados que se desincronicen.** El nombre se mantiene igual en ambos almacenes, la copia de lugares del
  archivo se actualiza con la base, y las herramientas declaradas se leen de la base al vuelo (antes había una copia
  guardada que quedaba vieja).
- **Modalidades** se guardan como las usan las ofertas y el puntaje: `onsite`, `hybrid`, `remote`.
- `update_profile` (reemplazo total) sigue disponible solo para el servidor MCP y el Onboarding; el agente de la app usa
  `update_profile_fields`. Experiencia, certificados y proyectos siguen en `update_cv`.
