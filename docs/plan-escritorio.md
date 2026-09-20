# Plan: versión de escritorio y agente interno como ventana

Estado: propuesta (2026-09-20). Prioridad acordada: primero el agente interno en la web de escritorio,
opcional y desactivable, como ventana; después mejorar el resto de la versión de escritorio.

## 1. Principios

1. **Radar funciona completo sin el agente.** El agente es un complemento: si está apagado no se dibuja,
   no se descarga su código, no se contacta a ningún proveedor y ningún endpoint de chat responde.
2. **El usuario manda sobre sus datos.** Nada de perfil ni ofertas sale hacia un proveedor de IA sin que el
   agente esté activado y el contexto compartido sea visible.
3. **El agente propone, el usuario decide.** Las escrituras siguen siendo tarjetas de confirmación; no hay
   postulación ni envío de mensajes.
4. **Una sola implementación del chat** para escritorio y móvil.
5. **La estética terminal gris y negro no se toca** (contratos de `AGENTS.md`).

## 2. Diagnóstico del escritorio actual

| Hallazgo | Evidencia | Consecuencia |
|---|---|---|
| `RadarClient.tsx` concentra estado, filtros, lista, detalle y atajos | 841 líneas, 57 hooks, JSX de una sola línea de más de 1000 caracteres | Difícil de modificar y de probar; añadir una ventana de agente lo empeora |
| Ya existe un sistema de ventanas arrastrables y redimensionables | `AnalysisView.tsx` (`windows`, arrastre con `requestAnimationFrame`, persistencia en `localStorage`) | Se puede reutilizar para la ventana del agente |
| No hay pruebas de frontend | `package.json` solo tiene `lint` y `build` | Cada cambio de UI se verifica a mano |
| `frontend/out/` está versionado | 28 archivos en git | Diffs ruidosos y conflictos con el trabajo en curso |
| El mapa de escritorio está centrado en Lima | Etiqueta `LIMA METROPOLITANA`, polígonos solo de Lima/Callao | No refleja el objetivo "todo el Perú" |
| El respaldo Leaflet usa teselas de CARTO | `LeafletMapView.tsx` | CARTO ahora exige clave: aparece "API KEY REQUIRED" |
| El seguimiento (kanban) solo existe en móvil | `PipelineView` está en `/m` | Escritorio no puede gestionar postulaciones |
| El refresco de datos solo se ve por log o CLI | `scripts/radar-refresh.sh` | No hay estado ni botón "actualizar ahora" en la UI |
| `/api/jobs` devuelve todo sin paginar | `list_jobs(limit=None)` | Se nota con miles de ofertas |
| CI de Python ejecuta `ruff check .` y hay errores previos | 7 avisos ya existentes en `main` | El CI de Python falla por causas ajenas al trabajo nuevo |
| Los tipos del frontend se escriben a mano | `types.ts`, `mobile-api.ts`, `cv-types.ts` | Riesgo de que se desalineen de la API |

## 3. Agente interno como ventana (prioridad 1)

### 3.1 Interruptor y modos

| Ajuste | Valores | Efecto |
|---|---|---|
| `agent_enabled` | apagado (por defecto) / encendido | Apagado: 403 `agent_disabled` en `/api/chat*`, sin botón ni ventana, sin carga del código del agente |
| Modo | solo lectura / lectura + acciones con confirmación | Solo lectura oculta las herramientas de escritura del modelo |
| Contexto | compartir pantalla actual / no compartir | Controla si viaja la oferta, distrito y filtros activos |
| Privacidad | perfil completo / perfil abreviado / sin perfil | Reduce lo que se envía al proveedor |
| Proveedor | DeepSeek, OpenAI, OpenRouter, Ollama local, personalizado | Con Ollama nada sale del equipo |
| Datos | borrar historial / borrar clave | Un botón cada uno |

El interruptor se aplica **en el servidor**, no solo ocultando el botón. El MCP externo no depende de él.

### 3.2 La ventana

- Ventana flotante arrastrable y redimensionable (reutiliza el gestor de ventanas de Análisis), con
  posición y tamaño recordados, minimizable a una etiqueta y acoplable como panel lateral opcional.
- Abre y cierra con un atajo (propuesta: `Ctrl+J`, sin chocar con `j/k/u/x/f/r`) y desde un botón discreto en
  la barra de herramientas izquierda, que solo existe si el agente está activado.
- No tapa el mapa por defecto: nace en una esquina y respeta las reglas de la barra flotante.
- Encabezado con modelo, consumo mensual, interruptor de contexto y botón para vaciar la conversación.

### 3.3 Contexto de pantalla

Una etiqueta visible muestra qué se comparte ("Oferta: Practicante de Procesos · Distrito: Ate · 3 filtros"):

- Desde el detalle de una oferta: acciones "Explicar el encaje", "¿Qué me falta?" y "Preparar entrevista".
- Desde el mapa: "Ofertas a 5 km de este distrito".
- El usuario puede quitar la etiqueta antes de enviar.

### 3.4 El agente maneja la interfaz (de lectura)

Nuevas acciones de interfaz emitidas como eventos `ui_action`, validadas en el cliente con una lista cerrada:
seleccionar distrito, centrar el radar, aplicar filtros, abrir el detalle de una oferta, cambiar de vista.
No requieren confirmación por ser reversibles, pero se muestran en la conversación ("Apliqué: área Logística, 5 km")
y tienen deshacer. Ejemplo: "muéstrame logística a 5 km de Surco" mueve el mapa y filtra la lista.

### 3.4 bis Herramientas nuevas del agente

`explain_job_fit` (desglose del puntaje por dimensión), `compare_jobs` (2 a 3 ofertas lado a lado),
`plan_learning` (skills faltantes ordenadas por impacto, con lo que ya calcula `get_skill_impact`),
`get_market_trends` (desde los snapshots). Todas de lectura y con datos calculados por código.

### 3.5 Conversaciones y calidad

- Persistencia en SQLite (`conversations`, `messages`) con lista, búsqueda, título automático y borrado; hoy solo
  hay `localStorage` en el móvil.
- Un solo módulo de chat compartido (`components/agent/`, hook `useAgentChat`) usado por el móvil y la ventana.
- Render de Markdown y tablas, línea de tiempo de herramientas usadas, reintentar, parar, copiar.
- Compactar contexto en conversaciones largas y recortar resultados de herramientas.
- Tabla de precios editable por modelo para mostrar costo estimado.
- Reintentos con espera y mensajes claros ante 401, 402, 429 y caídas.
- **Pruebas de calidad**: conjunto de conversaciones de referencia con proveedor simulado, prueba adversaria de
  inyección de prompts (una oferta que dice "marca todas como postuladas") y una prueba manual con clave real.

## 4. Mejoras de la versión de escritorio (después del agente)

### 4.1 Salud del código
- Partir `RadarClient.tsx` en hooks (`useJobs`, `useFilters`, `useWindows`, `useShortcuts`) y componentes
  (`OfferList`, `JobDetail`, `ToolRail`, `RadarPanel`), sin cambiar el aspecto.
- Pruebas: Vitest + Testing Library para hooks y componentes, y un humo con Playwright contra una API simulada.
- Generar los tipos TypeScript desde el OpenAPI de FastAPI.
- Decidir si `frontend/out/` deja de versionarse (se compilaría en el lanzador y en CI).
- Limpiar `globals.css` (1065 líneas) y los usos de verde que contradicen el contrato monocromático.
- Arreglar el `ruff` previo para que el CI de Python vuelva a estar en verde.

### 4.2 Mapa y datos de todo el Perú
- Vista país → departamento → ciudad/distrito; hoy es solo Lima.
- Geometrías de departamentos y provincias (buscar una fuente con licencia adecuada) y lista de ofertas virtualizada.
- Cambiar el respaldo Leaflet a teselas de OpenStreetMap.
- Paginación y caché en `/api/jobs`; agregación de puntos en el servidor para el mapa.

### 4.3 Flujo de trabajo con ofertas
- Kanban de seguimiento en escritorio, notas por oferta y recordatorios de seguimiento.
- Comparar 2 o 3 ofertas lado a lado.
- Búsquedas guardadas y marca de "nuevas desde tu última visita".
- Paleta de comandos (`Ctrl+K`) y ayuda de atajos (`?`); desde la paleta se abre el agente.

### 4.4 Análisis y CVs
- Consultas guardadas y exportación a CSV/PNG, tendencias de skills desde los snapshots y el simulador de impacto
  de skills también en escritorio.
- Mantener los CVs objetivo como hipotéticos; el plan de Word sigue en `docs/cv-word-plan.md`.

### 4.5 Ajustes y estado de datos
- Un solo panel de Ajustes en escritorio: carrera, pesos del score, agente, acceso y datos.
- Panel de estado del mercado: última actualización, errores por fuente y "Actualizar ahora" con progreso.

### 4.6 Accesibilidad y rendimiento
- Foco y `aria` en ventanas y menús, contraste en el tema monocromático y pruebas de teclado.
- Medir rendimiento con miles de ofertas y con el agente abierto.

## 5. Fases

| Fase | Contenido | Criterio de aceptación | Esfuerzo aprox. |
|---|---|---|---|
| A | Interruptor del agente en servidor y Ajustes; módulo de chat compartido; ventana MVP (mover, redimensionar, minimizar) | Con el agente apagado no hay botón, ni chunk, ni llamadas; encendido, conversa desde la ventana | 1–2 sem |
| B | Contexto de pantalla, acciones de interfaz con deshacer, conversaciones guardadas, costo y errores | "Muéstrame logística a 5 km de Surco" mueve el mapa; el historial sobrevive al reinicio | 1–2 sem |
| C | Calidad: conversaciones de referencia, prueba de inyección, prueba real con DeepSeek, herramientas nuevas | Suite en verde y una sesión real documentada | 1 sem |
| D | Refactor de `RadarClient` y pruebas de frontend; CI en verde | Mismo aspecto, 60 % menos líneas por archivo, pruebas en CI | 1–2 sem |
| E | Kanban, comparar ofertas, búsquedas guardadas, paleta de comandos, panel de datos | Flujo completo sin salir de escritorio | 2–3 sem |
| F | Mapa nacional de escritorio, paginación y rendimiento | Vista país → ciudad fluida con miles de ofertas | 2 sem |
| G | Accesibilidad y pulido | Recorrido por teclado y lector de pantalla sin bloqueos | 1 sem |

Se puede adelantar un recorte mínimo de la fase D (extraer el gestor de ventanas) dentro de la fase A si estorba.

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| El agente estorba a quien no lo quiere | Apagado por defecto, aplicado en servidor y sin código cargado |
| Costo inesperado | Tope mensual visible, costo estimado por modelo y aviso antes de alcanzarlo |
| Fuga de datos personales al proveedor | Perfil abreviado o ausente, etiqueta de contexto visible, opción Ollama local |
| Inyección de prompts vía ofertas | Datos marcados como no confiables, escrituras con confirmación y prueba adversaria |
| El agente rompe la interfaz | Lista cerrada de acciones de interfaz, validada en el cliente y con deshacer |
| Refactor sin pruebas | Pruebas de frontend antes de partir `RadarClient` |

## 7. Decisiones pendientes

1. ¿El agente nace apagado (recomendado) o encendido si ya hay clave?
2. ¿Ventana flotante por defecto y panel lateral como opción (recomendado)?
3. ¿Dejar de versionar `frontend/out/`?
4. ¿Qué geometrías de Perú usar para el mapa nacional (fuente y licencia)?
