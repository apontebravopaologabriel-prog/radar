# Roadmap

## V1 — implementada

- PostgreSQL y migraciones.
- Computrabajo MCP.
- JobSpy/Indeed opcional.
- Normalización y deduplicación.
- Clasificación heurística.
- Perfil separado.
- Score trazable.
- Consultas MCP para Hermes.
- Sin frontend ni postulaciones automáticas.

## V2 — implementada en esta iteración

- Candidatos de duplicado ambiguo.
- Requisitos estructurados más ricos.
- Observaciones históricas por oferta.
- Versionado del perfil profesional.
- Línea de carrera y eventos de aprendizaje.
- Herramientas MCP `get_job_history` y `get_career_timeline`.
- Extracción conservadora de salario desde descripciones con moneda explícita.
- Snapshots de mercado y seguimiento de postulaciones por MCP.
- Estado de aceptación de la oferta (`application_status`) y fecha de verificación, con filtro estricto para LinkedIn.
- Frescura configurable de 7 o 14 días y exclusión de ofertas no accionables en las consultas.

## Frontend geográfico — primera entrega implementada

- Aplicación Next.js independiente en `frontend/`.
- API HTTP FastAPI de solo lectura sobre las consultas existentes.
- Mapa de Lima con MapLibre y datos GeoJSON.
- Filtros por búsqueda, área, seniority, modalidad, salario y frescura.
- Clusters, heatmap y radios interactivos de 2, 5 y 10 km.
- Ubicaciones aproximadas por distrito o ciudad, con precisión visible.
- Vista `Distritos` con coropleta real de Lima/Callao, etiquetas de cantidad y
  resaltado del distrito seleccionado.
- Tema grafito oscuro para toda la interfaz, con scroll del explorador en ventanas
  reducidas.
- Fallback automático a Leaflet cuando el navegador no soporta WebGL2.
- Launcher `.desktop` que inicia servicios y abre Radar como web app independiente
  de Chromium.

## Frontend geográfico — siguiente etapa

- Persistir latitud, longitud, distrito y precisión en PostgreSQL.
- Geocodificación controlada durante la ingesta.
- Filtro por distrito y radio de distancia.
- Detalle completo de oferta y cambio de estado desde la interfaz.

## V2 — siguiente etapa
- Snapshots automáticos por semana/mes/año y reportes comparativos.
- Métricas por área, empresa y skill.
- Skill Gap priorizado.
- Mejorar el flujo de estados de aplicaciones y su auditoría desde CLI/MCP seguro.
- Pruebas de contrato por fuente.

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
