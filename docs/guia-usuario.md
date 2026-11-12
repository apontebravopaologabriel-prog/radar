# Guía de usuario de Radar

Radar es una aplicación local que reúne ofertas de empleo del Perú, las compara con tu perfil y te muestra dónde están
y qué te falta para alcanzarlas. Todo se guarda en tu computadora.

## Instalar

1. Descarga `Radar-Setup-<versión>.exe` desde la página de versiones del proyecto y ábrelo.
2. Si Windows muestra "SmartScreen", elige *Más información → Ejecutar de todos modos* (mientras el instalador no esté firmado). Compara el
   código SHA-256 con el de `SHA256SUMS.txt` si quieres verificarlo.
3. Abre **Radar** desde el menú Inicio. No necesitas instalar nada más.

## Primer uso

Radar te pregunta tu carrera (Ingeniería Industrial y Sistemas y Software vienen incluidas; puedes crear la tuya),
dónde buscas (Lima o cualquier ciudad del Perú), tu perfil y tus skills. Después pulsa **Actualizar mercado ahora**: tarda
unos minutos y trae ofertas recientes. Cada semana se actualiza solo mientras Radar está abierto.

## Qué puedes hacer

- **Mapa:** ofertas por distrito y a 2, 5 o 10 km de un distrito (`Radar`). Marca con ★ las que te interesen.
- **Mi búsqueda:** muestra primero los procesos donde hubo respuesta. Se agrupan por etapa. Pulsa el pin junto a una postulación para pasarla a Entrevista, o el icono de archivo para enviarla a Archivados. Archivados muestra y cuenta solo los últimos siete días calendario de Lima, incluido hoy. Puedes restaurar las filas visibles. «Buscar en historial» permite consultar archivos anteriores por puesto o empresa. El compromiso con la fecha más cercana se puede abrir desde el resumen y se marca si está vencido. Los cambios hechos desde un cliente MCP aparecen mientras Mi búsqueda está visible. Debajo, el ritmo de búsqueda y las postulaciones muestran la descripción guardada del aviso. «Me contactaron» abre un formulario desde una oferta; «Agregar proceso» permite empresa y puesto sin enlace. Abre una fila para ver la etapa, el próximo paso, la fecha y la nota. En Seguimiento, la flecha junto al icono de archivo devuelve la oferta vinculada a Postulaciones recientes. Cada fila muestra la fecha de publicación a la izquierda y el tiempo desde que postulaste a la derecha. «Sin respuesta · +14 d» filtra las postulaciones pendientes. Debajo aparecen ocho postulaciones recientes; «Ver todas» abre el historial con búsqueda. Abre una fila para consultar la oferta, registrar una respuesta o deshacer el registro. El detalle incluye ubicación, modalidad, salario, fecha y estado de publicación. Pulsa el título para abrir el aviso original o la descripción para expandirla.
- **Análisis:** resumen de la misma selección del mapa: ofertas, empresas, competencias, publicaciones y sueldos. Pulsa una barra para consultar sus ofertas. «Comparar» permite elegir hasta cuatro ofertas guardadas o postuladas; pulsa una celda para revisar el requisito, su motivo y la cita del aviso. Las vistas guardadas conservan los filtros y usan un periodo relativo; Consultas consulta la base completa sin los filtros del mapa.
- **Mi CV (opcional, desde Ajustes → Abrir Mi CV y documentos):** abre primero «Mis datos» para revisar tu perfil. Desde una oferta pulsa «Preparar CV» para ver y descargar el documento; los archivos preparados siguen en «Documentos». «Editar en detalle» abre el editor opcional.
  Los candidatos ideales son *hipotéticos* y nunca se exportan.
- **Agente (opcional):** un asistente de chat que usa tu propia clave de API (DeepSeek, OpenAI, OpenRouter u Ollama).
  En sus respuestas, el puesto de cada oferta es un enlace: al pulsarlo se abre esa oferta en el detalle del mapa, y
  «portal ↗» va a la publicación original. Está apagado por defecto. Todo lo que cambie datos te pide confirmación. Nunca postula ni envía mensajes.

## Conectar tu asistente de IA (Claude, Cursor, Gemini)

*Ajustes → Conectar IA*: elige tu cliente y pulsa **Instalar**; Radar escribe su configuración (guarda una copia del archivo
anterior). Reinicia el cliente y pregúntale, por ejemplo, "¿qué ofertas de datos hay cerca de Miraflores?". Si prefieres
hacerlo a mano, copia la configuración que se muestra.

## Privacidad

- Tus datos (perfil, CV, foto, conversaciones) viven en `%LOCALAPPDATA%\radar` y no se envían a ningún servidor de Radar.
  No hay telemetría.
- Solo sale de tu equipo lo que tú envías a tu proveedor de IA (si activas el agente) y las búsquedas a los portales de empleo.
- La clave de tu proveedor se guarda en el Administrador de credenciales de Windows.
- Desinstalar Radar **no** borra tus datos; para borrarlos elimina esa carpeta.

## Avisos

- Radar lee páginas públicas de portales de empleo, que tienen sus propios términos. Úsalo con moderación.
- La ubicación de las ofertas es aproximada (por distrito o ciudad).
- Revisa siempre una oferta en su portal original antes de actuar.

## Problemas frecuentes

- **No aparecen ofertas:** pulsa *Actualizar mercado ahora* y espera unos minutos; revisa tu conexión.
- **Un portal falla:** Radar sigue con los demás; el resultado final indica qué paso falló.
- **El mapa sale en blanco:** recarga la ventana (Ctrl+R). Si sigue igual, cierra y abre Radar; si persiste, revisa que tu
  navegador tenga WebGL2 y mira `docs/troubleshooting.md`.
- **El agente no responde:** revisa en Ajustes → Agente que esté activado, que la clave sea válida y que no hayas llegado al tope mensual.
- **Respaldo:** `radar-cli backup` guarda una copia consistente en la carpeta `backups` de tus datos.
