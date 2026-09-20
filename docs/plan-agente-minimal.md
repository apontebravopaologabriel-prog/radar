# Plan de diseño: el agente tan minimal como abrir Claude Code

Estado (2026-09-20): la mayor parte de la base está implementada; este documento fija el criterio de diseño y lo que falta.

## 1. Decisión

El agente tiene **dos modos y el mismo contenido**: ventana flotante (arrastrable, redimensionable, minimizable) y **panel fijado a la
derecha** que hace que el mapa ceda el ancho. Se cambia con `/fijar` (o `/pin`) o con el botón de la barra del agente. Por defecto
nace flotante; el modo y el ancho se recuerdan. Los dos comparten la misma terminal, así que no hay funciones distintas por modo.

## 2. Principios

1. **Una sola superficie: la línea de comandos.** Todo lo que se puede hacer con un botón se puede hacer escribiendo `/`.
2. **Cero cromo.** Sin burbujas, tarjetas ni botones grandes: líneas de texto con un prefijo de una sola letra/símbolo.
3. **Información a demanda.** Contexto y costo viven en una línea de estado discreta y se detallan con `/contexto` y `/costo`.
4. **Teclado primero**, pero cada acción sigue siendo alcanzable con el toque (móvil).
5. **Estética Radar**: monoespaciada, grises y negro, sin acentos de color; el símbolo del agente (anillo, barrido y punto) es la única "marca".
6. **Lo local no cuesta tokens**: los comandos que consultan tus datos no llaman al modelo.

## 3. Anatomía de la pantalla

```text
◉ radar                                   ⇥  –  ×      ← barra mínima (símbolo, fijar, minimizar, cerrar)
❯ ¿qué hay nuevo hoy?                                   ← tú
  ⎿ consultó get_today_feed                             ← herramienta usada (tenue)
◉ 5 ofertas … (Markdown, tablas)                        ← agente
▸ /contexto → medidor                                   ← resultado local (sin tokens)
❯ _                                                     ← prompt
/ comandos · ↑ historial      deepseek-chat · ctx 9% · mes 54%   ← pie: ayuda y estado
```

| Elemento | Regla |
|---|---|
| Prefijos | `❯` tú · `◉` agente (gira mientras trabaja) · `▸` resultado local · `⎿` herramienta · `✕` error |
| Estado | Una línea al pie: modelo, % de contexto y % del tope mensual; `lectura` si está en solo lectura |
| Aprobación | Línea de acción propuesta con `y` / `n`; no se ejecuta nada que escriba sin ella |
| Menú `/` | Lista sobre el prompt; ↑↓ navegan, Tab completa, Esc cierra |
| Vacío | Una línea de bienvenida y cinco atajos en texto subrayado, sin botones |

## 4. Comandos (nombres de Claude Code, con alias en español)

| Comando | Hace | Tokens |
|---|---|---|
| `/context` | Medidor del contexto: sistema y herramientas vs. mensajes, total de la sesión | 0 |
| `/compact [foco]` | Resume la conversación con el modelo (opcionalmente priorizando un foco) y sigue desde el resumen | sí (una llamada) |
| `/cost` (`/usage`, `/tokens`) | Uso mensual frente al tope | 0 |
| `/model [nombre]` | Ver o cambiar el modelo | 0 |
| `/clear` (`/new`) | Conversación nueva (la anterior queda guardada) | 0 |
| `/resume`, `/open <n>`, `/delete [all]` | Conversaciones guardadas en la base local | 0 |
| `/export` | Descarga la conversación en Markdown | 0 |
| `/memory [add\|rm\|clear]`, `# texto` | Preferencias que el agente recuerda en cada conversación (como CLAUDE.md) | 0 |
| `/doctor` | Diagnóstico: ofertas, agente, base de datos, actualización en curso | 0 |
| `/tools` (`/mcp`) | Herramientas que el agente puede usar (lectura y escritura) | 0 |
| `/pin` | Alterna ventana flotante y panel a la derecha | 0 |
| `/config`, `/copy`, `/exit` | Ajustes, copiar la última respuesta, cerrar | 0 |
| `/today`, `/map`, `/pipeline`, `/skills`, `/status`, `/profile`, `/refresh` | Consultas y acciones de Radar | 0 |
| `/readonly`, `/disable` | Controles de seguridad del agente | 0 |
| `/init`, `/explain`, `/plan`, `/summary` | Piden al agente configurar o analizar | sí |

Funciones de Claude Code adoptadas: `/context`, `/compact [foco]`, `/cost`, `/model`, `/clear`, `/resume`, `/export`, `/memory` (y `#`),
`/doctor`, `/tools`, `/config`, `/init`, `/copy`, `/exit`. Se dejaron fuera las que no tienen equivalente en Radar (edición de archivos, `bash`, hooks, agentes).
Otras que podrían sumar: `/permissions` (lista y cambio granular de escrituras), `/rewind` (deshacer la última acción guardada), `/review` (revisión de la
semana: nuevas, cambios y seguimiento) y `@` para mencionar una oferta por id.

## 5. Lo que falta

| # | Mejora | Criterio |
|---|---|---|
| 1 | Compactación automática al pasar de ~80 % del contexto, con aviso de una línea | Nunca se corta una conversación por límite de contexto |
| 2 | Comandos personalizados del usuario (`/mi-comando` que guarda un prompt) | Se definen desde Ajustes y aparecen en el menú `/` |
| 3 | Atajos: `Ctrl+L` limpia, `Ctrl+C` detiene, `Shift+Tab` alterna solo lectura | Documentados en `/ayuda` |
| 4 | Vista compacta de herramientas (`⎿`) con expansión bajo demanda (`/herramientas`) | Ver argumentos y tamaño del resultado sin ruido por defecto |
| 5 | Búsqueda en el historial (`/buscar <texto>`) | Encuentra una conversación por contenido |
| 6 | Coste estimado en dinero con una tabla de precios editable | Cifra aproximada en `/costo` |
| 7 | Contexto de pantalla (oferta y distrito seleccionados) | Bloqueado hasta que `RadarClient.tsx` esté commiteado |
| 8 | Ajuste fino del panel fijado en pantallas estrechas (se vuelve ventana bajo 900 px) | Sin el mapa aplastado |

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| El mapa no responde bien al cambio de ancho | Se emite `resize` al fijar; se verificó a 1440 px, falta probar en pantallas pequeñas |
| Compactar pierde detalles | El resumen conserva cifras, ids y pendientes; el historial completo sigue guardado en la conversación mostrada |
| Medidor impreciso | Se muestra "estimado" tras compactar y la ventana es configurable |
