# Seguridad y cumplimiento

- No guardes `.env` en Git.
- No guardes cookies de Computrabajo en el repositorio.
- La base de datos activa es un archivo SQLite local, sin puerto de red expuesto. El
  `legacy/postgres/docker-compose.yml` con PostgreSQL es infraestructura heredada de antes de la migración a SQLite;
  si se levanta por algún motivo, debe seguir expuesto solo en `127.0.0.1`.
- No expongas el MCP stdio públicamente sin autenticación.

Radar V1 no tiene herramientas de postulación ni de envío de mensajes. El agente puede modificar el
perfil (`update_profile_fields`) y el CV real (`update_cv`, `close_gap`), pero nunca sin que la persona
lo apruebe: ver la lista de herramientas que escriben más abajo.

Los conectores que leen páginas públicas siguen sujetos a los términos de cada plataforma. Revisa las condiciones vigentes antes de aumentar frecuencia, volumen o alcance, especialmente en LinkedIn y Computrabajo.

El perfil puede contener educación, skills y evidencia profesional. Minimiza los datos almacenados y conserva únicamente lo necesario para el score.

Reglas de calidad:

- `NULL` significa dato no disponible.
- Ausencia de salario no equivale a cero.
- Toda clasificación debe conservar evidencia.
- Cantidad de ofertas no equivale a competencia.
- Revisa manualmente recomendaciones antes de actuar.


Los CVs objetivo (`docs/target-profiles.md`) son hipotéticos: llevan marca fija, no se exportan y su
API es de solo lectura. `cv_master.json` y `photo.jpg` contienen datos personales; viven en
`~/.local/share/radar/`, fuera de Git, y la API nunca acepta una ruta de archivo del cliente.

El CV **real** descargable (`docs/cv-word-plan.md`) es otra cosa: `build_cv` genera DOCX/PDF a partir
de `cv_master.json`, sin inventar ni reformular contenido, y guarda los archivos en
`~/.local/share/radar/cvs/<fecha>/`, siempre con nombre nuevo (nunca sobrescribe). La API para
descargarlos (`GET /api/cv/files/...`) solo sirve rutas dentro de esa carpeta y con extensión `.docx`
o `.pdf`; una ruta con `..` o de otra carpeta se rechaza. La foto de perfil (`POST /api/me/photo`) se
valida con Pillow (no solo por su extensión), se limpia de metadatos EXIF —que pueden llevar ubicación
GPS— y se redimensiona antes de guardarse; un archivo corrupto, demasiado pesado o de otro formato se
rechaza sin escribir nada.


## Agente de chat y acceso remoto

- Las descripciones de ofertas son texto de terceros. El agente las recibe marcadas como
  `datos_externos_no_confiables` y su prompt las trata como información, nunca como instrucciones.
- Las herramientas que escriben (favoritos, seguimiento, perfil, CV, plan de cierre, CV descargable, carrera,
  memoria, captura, temporizador, mantenimiento, pesos y reclasificación) no se ejecutan dentro del bucle del
  agente: el usuario las aprueba en `/api/chat/confirm`. El modo **auto** solo aprueba solas cuatro acciones de
  seguimiento personal (`favorite_job`, `track_job_application`, `remember_user`, `record_career_event`); todo lo
  demás —incluidas `update_profile_fields`, `close_gap` y `build_cv`, que se añadieron después de fijar esa
  lista— sigue pidiendo confirmación. En modo **plan** y en **solo lectura** el servidor no ofrece las
  herramientas de escritura y rechaza cualquier llamada. No existen herramientas que envíen mensajes ni postulen.
  `ingest_jobs` y `save_target_profile` no se exponen al chat.
- `update_profile_fields` edita solo los campos que se le pasan explícitamente (nunca borra por omisión), valida
  todo antes de escribir y, si falla a medio camino, revierte el archivo del CV a como estaba: nunca deja el
  perfil a medias entre los dos almacenes donde vive (`cv_master.json` y SQLite).
- El agente no puede cambiar la clave de API, el modo solo lectura ni el tope de tokens: son ajustes de la persona.
- Las acciones de sistema son listas cerradas: `run_maintenance` solo acepta `backup`, `repair_data`, `expire_stale`,
  `check_applications` y `market_snapshot`; `set_refresh_schedule` solo edita `radar-refresh.timer` (1 a 30 días);
  `update_cv` valida el formato de cada sección y guarda una copia previa de `cv_master.json`. Nada de esto borra
  ofertas, y la reclasificación deja un JSON reversible.
- `get_my_cv` envía tu CV completo al proveedor de LLM cuando la pregunta lo necesita; el resumen fijo del prompt
  incluye solo el nombre y el titular.
- Las conversaciones (`conversations`) y la memoria (`agent_memories`) viven en la base local. El agente solo busca en
  conversaciones anteriores cuando la persona alude a ellas, y devuelve fragmentos.
- El perfil y las ofertas consultadas viajan al proveedor de LLM elegido: usa un proveedor en el que
  confíes o Ollama local para no enviar datos a terceros.
- `RADAR_ACCESS_TOKEN` activa una clave de acceso para `/api/*` (cookie `HttpOnly`, `SameSite=Strict`,
  5 intentos por minuto). Es protección para uso personal, no un sistema multiusuario.
- Las claves de proveedores viven en `secrets.json` (`0600`), fuera de la base que consulta el editor SQL.
