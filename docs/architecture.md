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
Hermes
  ↓ MCP stdio
Radar MCP (FastMCP)
  ↓
Pipeline Python
  ├─ Computrabajo MCP por stdio
  ├─ JobSpy directo desde Python
  ├─ refresco systemd de ocho familias de búsqueda cada 6 horas
  ├─ normalización
  ├─ clasificación heurística
  ├─ deduplicación por fingerprint
  └─ scoring determinístico
  ↓
PostgreSQL
```

La interfaz web usa una API HTTP, sin acceder directamente al
MCP ni a PostgreSQL:

```text
Browser
  ↓ HTTP GET / PATCH
Radar API (FastAPI, puerto 8100)
  ↓ reutiliza consultas
PostgreSQL
```

Hermes es la interfaz conversacional. Python coordina fuentes, transforma respuestas, clasifica texto, calcula fingerprints y persiste. PostgreSQL es la fuente de verdad.

La clasificación actual es heurística y usa alias definidos en `src/radar/classify.py`; el enriquecimiento de sector, modalidad, salario y horario también conserva evidencia y deja `NULL` cuando no hay datos confiables. Todavía no depende de un LLM.

Las consultas de la vista web aplican frescura por `published_at` y excluyen únicamente las ofertas ocultadas por el usuario. No aplican una exclusión especial por `is_active`, estado de aplicación o fuente LinkedIn. Las recomendaciones MCP mantienen sus propias reglas de calidad y verificación de fuente. Las ofertas no accionables permanecen en PostgreSQL para historial. `job_areas` permite consultar y agrupar la vista por área industrial.

## Estructura

```text
src/radar/
├── classify.py             # áreas, skills y seniority
├── normalize.py            # limpieza y fingerprints
├── scoring.py              # score personal determinístico
├── pipeline.py             # selección de fuente y ejecución
├── sources/                # adaptadores externos
├── db/                     # conexión, escritura y consultas
└── mcp/server.py           # interfaz para Hermes
frontend/
├── app/radar/              # pantalla principal del explorador
├── components/RadarClient.tsx # filtros, lista, selección y estado de la vista
├── components/MapView.tsx  # MapLibre, distritos, coropleta, clusters y radios
├── components/LeafletMapView.tsx # fallback sin WebGL2
├── components/SkillsView.tsx # demanda de skills, perfil y ruta sugerida
├── app/globals.css         # tema grafito, layout y scroll del explorador
└── lib/api.ts              # cliente HTTP de Radar API
```

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
- La vista `Skills` consulta `/api/skills/overview` y cruza la demanda reciente de
  `job_skills` con el nivel, interés y evidencia declarados en `user_skills`.
  Muestra una constelación de skills y una ruta sugerida; el progreso es orientativo
  hasta que se registren evidencias verificables como proyectos o eventos de carrera.

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

Una oferta antigua se marca inactiva o expirada; no se elimina. Así se pueden comparar meses y años, detectar ofertas nuevas o modificadas y evaluar si una skill aprendida mejora el encaje posterior. PostgreSQL sigue siendo suficiente como fuente de verdad; la búsqueda vectorial queda para una etapa posterior, si el volumen y las consultas semánticas lo justifican.
