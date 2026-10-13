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
- **Análisis:** preguntas sobre el mercado (skills más pedidas, salarios, empresas) con tablas y gráficos.
- **CVs:** para cada oferta con ★ ves qué te falta, un plan para cerrarlo y puedes generar tu CV real en Word y PDF.
  Los candidatos ideales son *hipotéticos* y nunca se exportan.
- **Agente (opcional):** un asistente de chat que usa tu propia clave de API (DeepSeek, OpenAI, OpenRouter u Ollama).
  Está apagado por defecto. Todo lo que cambie datos te pide confirmación. Nunca postula ni envía mensajes.

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
- **El agente no responde:** revisa en Ajustes → Agente que esté activado, que la clave sea válida y que no hayas llegado al tope mensual.
- **Respaldo:** `radar-cli backup` guarda una copia consistente en la carpeta `backups` de tus datos.
