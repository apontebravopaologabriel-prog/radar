# Arquitectura de Radar V1/V2

## Objetivo

Radar recopila ofertas orientadas inicialmente a Ingeniería Industrial en Perú. La V1 demuestra:

```text
buscar → normalizar → clasificar → deduplicar → observar → guardar → consultar → recomendar → evolucionar
```

El frontend geográfico inicial existe como una aplicación web separada; no se
automatizan postulaciones.

## Componentes

```text
Agente (Antigravity, Claude Code, Hermes…)
  ↓ MCP stdio
Radar MCP (FastMCP)
  ↓
Pipeline Python
  ├─ Computrabajo MCP por stdio
  ├─ JobSpy directo desde Python
  ├─ refresco systemd diario de dieciséis búsquedas en Indeed y Computrabajo
  ├─ normalización
  ├─ clasificación heurística
  ├─ deduplicación por fingerprint
  └─ scoring determinístico
  ↓
SQLite
```

La interfaz web usa una API HTTP, sin acceder directamente al
MCP ni a SQLite:

```text
Browser
  ↓ HTTP GET / PATCH
Radar API (FastAPI, puerto 8100)
  ↓ reutiliza consultas
SQLite
```

El agente conectado por MCP (Antigravity por defecto; el servidor es independiente del cliente) es la interfaz conversacional. Python coordina fuentes, transforma respuestas, clasifica texto, calcula fingerprints y persiste. SQLite es la fuente de verdad.

La clasificación actual es heurística: `src/radar/classify.py` acumula un puntaje por área a partir de las reglas del paquete de carrera (`careers/packs/*.json`) y `src/radar/taxonomy.py` asigna la relevancia (ver [database.md](database.md#clasificación-profesional)); el enriquecimiento de sector, modalidad, salario y horario también conserva evidencia y deja `NULL` cuando no hay datos confiables. Cada oferta recibe además una relevancia trazable (`core`, `adjacent` u `out_of_focus`) para priorizar el mercado de Ingeniería Industrial sin borrar ofertas. Todavía no depende de un LLM.

Las consultas de la vista web aplican frescura por `published_at`, muestran ofertas activas y
canónicas, y excluyen las ocultadas por el usuario. `job_sources` conserva todas las URLs de una
misma oferta, mientras `canonical_fingerprint` evita crear otra fila para el mismo identificador
normalizado. Las ofertas no accionables permanecen en la base para historial. `job_areas` permite
consultar y agrupar la vista por área profesional, incluida `Ventas / Comercial`.

## Estructura

```text
src/radar/
├── classify.py             # áreas, skills y seniority
├── normalize.py            # limpieza y fingerprints
├── scoring.py              # score personal determinístico
├── pipeline.py             # selección de fuente y ejecución
├── sources/                # adaptadores externos
├── db/                     # conexión, escritura y consultas
├── cv_targets.py           # CVs objetivo hipotéticos: lectura, validación, matriz y distancias
├── cv_edit.py              # edición por texto de cv_master.json (validación, copia previa, escritura atómica)
├── maintenance.py          # auditoría y reclasificación de áreas, con huella de las reglas
├── system.py               # estado del sistema, temporizador systemd y tareas de mantenimiento (lista cerrada)
├── refresh.py              # captura en segundo plano (general y por lugar)
├── tools.py                # registro único de herramientas: MCP y chat
├── agent/                  # bucle del agente, proveedor, memoria, historial de conversaciones y soul.md
└── mcp/server.py           # servidor MCP para cualquier agente
frontend/
├── app/radar/              # pantalla principal del explorador
├── components/RadarClient.tsx # filtros, lista, selección y estado de la vista
├── components/MapView.tsx  # MapLibre, distritos, coropleta, clusters y radios
├── components/LeafletMapView.tsx # fallback sin WebGL2
├── components/AnalysisView.tsx # consultas SQL de solo lectura y sus resultados
├── components/CvView.tsx   # CVs objetivo: foto, matriz de brechas, comparación y CV por puesto
├── app/globals.css         # tema grafito, layout y scroll del explorador
└── lib/api.ts              # cliente HTTP de Radar API
```

El agente de chat vive en `src/radar/agent/` y `frontend/components/agent/`. El proveedor es
OpenAI-compatible y conserva el `reasoning_content` de DeepSeek durante llamadas a herramientas.
El selector de modelos usa el catálogo habilitado por proveedor: muestra un nombre legible, pero
persiste el identificador real enviado a la API. En DeepSeek, por ejemplo, `DeepSeek V4.1 Flash`
corresponde a `deepseek-flash` y `DeepSeek V4 Pro` a `deepseek-v4-pro`. `/model` y `/models`
abren el selector de modelo; `/effort` abre el selector de `auto`, `none`, `low`, `high` y `max`.

El chat recibe un contexto explícito de la interfaz en cada turno, no una captura de pantalla ni
el DOM: vista (`map`, `analysis` o `cvs`), modo del mapa, distrito y radio seleccionados (con el conteo propio del
distrito, `districtJobs`), filtros, oferta activa y contador de resultados. Análisis también publica si terminó de
restaurar sus ventanas y un resumen de cada una. El usuario elige cuánto se envía (apagado, selección o completo) y
las menciones con `@` viajan aparte como lista explícita. El prompt lo trata como dato de navegación, no como
instrucciones.

El prompt de sistema se compone de las reglas operativas (`SYSTEM_PROMPT` en `agent/loop.py`), el carácter
(`agent/soul.md`, basado en el ISE BoK), el nombre y el titular del CV de la persona, sus notas de memoria y, cuando
corresponde, el aviso de reglas de clasificación desactualizadas y el bloque del modo plan. Un turno tiene hasta 8
pasos; en el último se retiran las herramientas para cerrar con lo obtenido. Los resultados de herramientas se recortan
por elementos y los de turnos anteriores solo conservan un extracto. Las herramientas de escritura nunca se ejecutan
dentro del bucle: se devuelven como `pending` y el usuario las aprueba en `/api/chat/confirm`; en modo plan (o solo
lectura) el servidor ni siquiera las ofrece.

Para comparar el distrito seleccionado con otro existe `compare_places` (volumen, áreas, modalidad, seniority, salario
mediano y señales de producción como una dimensión más) y `get_place_profile` para un solo lugar. La referencia
completa del agente (herramientas, modos, interfaz y memoria) está en [agente.md](agente.md).

## Decisiones deliberadas

- Los conectores no son la fuente de verdad.
- El score no lo decide el LLM.
- `description_raw` y `raw_payload` se conservan.
- Los duplicados no se borran automáticamente.
- Las cookies de Computrabajo no forman parte de V1.
- LinkedIn no se activa por defecto por sus restricciones de automatización.
- La API web limita CORS a localhost; expone consultas de mercado y un PATCH para el estado personal de una oferta.
- La vista `Distritos` usa límites de Lima/Callao, color por cantidad filtrada y
  selección sincronizada con el ranking y la lista de ofertas.
- Las coordenadas actuales se infieren de forma conservadora desde distrito o
  ciudad y se conserva el nivel de precisión en la respuesta.
- El frontend detecta WebGL2 antes de crear MapLibre. Cuando no está disponible,
  renderiza Leaflet con teselas oscuras; así el fallo de contexto WebGL no impide
  consultar el mercado.
- El tema visual es grafito oscuro inspirado en ChatGPT: `#212121` como fondo de
  trabajo, `#171717` para navegación y `#2f2f2f` para controles y tarjetas.
- El sidebar del explorador usa scroll vertical propio y la lista de ofertas tiene
  un límite interno para que ranking, ofertas y detalles sigan accesibles en ventanas
  reducidas.
- Las ofertas pueden ocultarse desde el detalle con un motivo y restaurarse desde la vista de ocultas; el estado vive en `job_user_status` y no altera `jobs`.
- Las ofertas pueden guardarse con una estrella; Favoritos consulta `job_user_favorites` y es independiente de las ofertas ocultas.
- La barra superior fue eliminada; `Radar` queda como encabezado principal del explorador y el mapa usa todo el alto disponible.
- La vista `Análisis` envía SQL a `/api/analytics/query`, que solo admite consultas de lectura, y
  `/api/analytics/schema` describe las tablas disponibles.
- La vista `CVs` lee `/api/cv/profile`, `/api/cv/selection`, `/api/cv/targets` y `/api/cv/photo`. Los objetivos son los
  favoritos (`job_user_favorites`); `cv_baseline.py` calcula su brecha base contra el perfil real. Los datos son archivos
  locales junto a la base de datos (`cv_master.json`, `targets/*.json`, `photo.jpg`), fuera de Git y
  fuera de SQLite; la API solo sirve la foto de esa ruta fija. Diseño y reglas en
  `docs/target-profiles.md`.

## Frontera con T

Radar conserva la fuente de verdad profesional: ofertas, demanda, perfil,
skills declaradas, eventos de carrera y estado histórico. T no replica esas
tablas. T Knowledge aporta libros, PDFs, clippings, notas y provenance para
investigar o preparar la práctica; Plane conserva el proyecto y sus entregables;
IAI conserva el contexto episódico de las sesiones.

La futura integración debe relacionar una skill de Radar con una capacidad
humana observable y una evidencia revisable. La frecuencia de una skill, un
curso terminado o una salida generada por IA no deben elevar automáticamente
el nivel profesional.

## Memoria profesional

Radar conserva tres líneas temporales relacionadas:

- `job_observations`: cada captura de una oferta por fuente, incluso si la oferta ya existía.
- `profile_versions`: cada actualización explícita del perfil, con sus skills, objetivos y preferencias de ese momento.
- `career_events` y `application_events`: empleo, formación, proyectos, entrevistas, logros y cambios de estado.

Una oferta antigua se marca inactiva o expirada; no se elimina. Así se pueden comparar meses y años, detectar ofertas nuevas o modificadas y evaluar si una skill aprendida mejora el encaje posterior. SQLite sigue siendo suficiente como fuente de verdad; la búsqueda vectorial queda para una etapa posterior, si el volumen y las consultas semánticas lo justifican.
