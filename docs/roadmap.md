# Roadmap

## V1 — implementada

- PostgreSQL y migraciones (migrado posteriormente a SQLite nativo; ver `docs/database.md`).
- Computrabajo MCP.
- JobSpy/Indeed opcional.
- Normalización y deduplicación.
- Clasificación heurística.
- Perfil separado.
- Score trazable.
- Consultas MCP para agentes (opcional, para agentes externos).
- Sin postulaciones automáticas; el frontend geográfico se documenta en la sección correspondiente.

## V2 — implementada en esta iteración

- Candidatos de duplicado ambiguo.
- Requisitos estructurados más ricos.
- Observaciones históricas por oferta.
- Versionado del perfil profesional.
- Línea de carrera y eventos de aprendizaje.
- Herramientas MCP `get_job_history` y `get_career_timeline`.
- Extracción conservadora de salario desde descripciones con moneda explícita.
- Snapshots de mercado y seguimiento de postulaciones por MCP.
- Estado de aceptación de la oferta (`application_status`) y fecha de verificación, con requisitos estrictos para recomendaciones de LinkedIn.
- Frescura configurable de 7 o 14 días y exclusión de ofertas no accionables en las consultas.

## Frontend geográfico — primera entrega implementada

- Aplicación Next.js independiente en `frontend/`.
- API HTTP FastAPI para consultas de mercado y estado personal de ofertas.
- Mapa de Lima con MapLibre y datos GeoJSON.
- Filtros por búsqueda, área, seniority, modalidad, salario y frescura.
- Clusters, heatmap y Radar funcional con centro fijo por distrito, zoom automático, radios de 2,
  5 y 10 km, filtro Haversine y barrido visual.
- Ubicaciones aproximadas por distrito o ciudad, con precisión visible.
- Vista `Distritos` con coropleta real de Lima/Callao, etiquetas de cantidad y
  resaltado del distrito seleccionado.
- Tema grafito oscuro para toda la interfaz, con scroll del explorador en ventanas
  reducidas.
- Fallback automático a Leaflet cuando el navegador no soporta WebGL2.
- Launcher `.desktop` que inicia servicios y abre Radar como web app independiente
  de Chromium.
- Ocultar/restaurar ofertas desde la interfaz, con motivo persistido en `job_user_status`.
- Vista `Skills` con demanda de mercado desde SQLite, cruce contra el perfil y
  ruta visual de aprendizaje por etapas (reemplazada después por `Análisis`; el endpoint
  `/api/skills/overview` se conserva).

## Frontend geográfico — siguiente etapa

- Persistir latitud, longitud, distrito y precisión en SQLite.
- Geocodificación controlada durante la ingesta.
- Persistencia de coordenadas precisas y geocodificación controlada para que el radio de distancia
  deje de depender de centroides aproximados por distrito/ciudad.
- Detalle completo de oferta y cambio de estado desde la interfaz.

## Agente — implementado

- Identidad basada en el ISE BoK, modos manual/auto/plan, menciones con `@`, memoria durable y búsqueda en conversaciones.
- Interfaz estilo terminal (selectores, atajos, ventanas temporales, herramientas plegables); ver [agente.md](agente.md).
- Mantenimiento desde el agente: auditoría y reclasificación de áreas, respaldos, temporizador de captura, pesos y edición del CV por texto.
- Captura enfocada en un distrito (`refresh_market`) y captura automática cada 7 días.
- Pendiente: carga de herramientas bajo demanda (hoy 40 en el chat, unos 5.000 tokens por mensaje), streaming por líneas y vocabulario más rico para las áreas con pocas ofertas (trabajo, producto, sistemas).

## V2 — siguiente etapa
- Snapshots automáticos por semana/mes/año y reportes comparativos.
- Métricas por área, empresa y skill.
- Skill Gap priorizado con evidencias de proyectos, cursos y eventos de carrera.
- Competencias (la vista `Skills` fue retirada; su rol lo cubren `Análisis` y `CVs`): separar skill de mercado, capacidad humana,
  asistencia de IA y evidencia verificable.
- Añadir career tracks y roles adyacentes sin ampliar inicialmente el foco más allá de
  Ingeniería Industrial y sus áreas cercanas.
- Mejorar el flujo de estados de aplicaciones y su auditoría desde CLI/MCP seguro.
- Pruebas de contrato por fuente.

## CVs objetivo — V0 de solo lectura implementada

- Perfil real estructurado y esquema JSON del CV ideal por oferta.
- Herramientas MCP: contexto, guardado, brechas, agregación y distrito más cercano.
- Objetivos = favoritos, con brecha base por código y ranking de cercanía (implementado).
- Vista `CVs`: matriz de brechas, comparación de 2 a 4 puestos, render con foto y plan de cierre.
- Detalle en `docs/target-profiles.md`.

## V3 — opcional

- Dashboard Power BI.
- Reportes semanales.
- Exportación curada a Obsidian.
- Alertas programadas.
- Fuentes adicionales mediante API, RSS o ATS públicos.

## Fuera de alcance

- Postulación automática.
- Envío automático de mensajes.
- Bypass de CAPTCHA o controles de acceso.
- Geocodificación exacta persistida antes de incorporar coordenadas confiables en SQL.

El CV real en Word (plantillas, verificación y edición) está diseñado en `docs/cv-word-plan.md`.
