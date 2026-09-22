# Plan de rendimiento: que Radar se sienta tan ligero como una terminal

Estado (2026-09-20). Mediciones con Chromium sin cabeza (render por software, más lento que una GPU real) sobre tu base real
(1 885 ofertas vigentes). Sirven para comparar antes y después, no como cifras absolutas de tu equipo.

## 1. Qué medí y qué encontré

| Medida | Antes | Después | Causa |
|---|---|---|---|
| `GET /api/jobs` (14 días) | 6,2 MB · 4,0 s | 1,6 MB (gzip) · 0,16 s | Falta de índice en `job_sources(job_id)`: cada oferta escaneaba toda la tabla; sin compresión |
| `GET /api/today` | 4,6 s | 0,01 s | El mismo índice |
| Abrir una conexión a la base | 2,2 ms | 0,5 ms | Las garantías del esquema se ejecutaban en cada conexión |
| Arrastrar la ventana del agente (60 movimientos) | 60 relayouts, 144 recálculos de estilo | 1 relayout, 84 recálculos | `left/top` y `setState` en cada movimiento; ahora `transform` y estado al soltar |
| Estirar el panel fijado (60 movimientos) | 22,7 s, 49 tareas largas (19,8 s), fotograma medio 328 ms | 2,8 s, 2 tareas largas (0,3 s), fotograma medio 37 ms | El mapa se redimensionaba en cada píxel; ahora solo cambia el panel y el mapa se reajusta al soltar |
| DOM de `/radar` | 52 516 nodos (1 146 tarjetas) | 3 822 nodos (60 tarjetas; carga más al bajar) | Lista por tramos con `IntersectionObserver` |
| Memoria JS de `/radar` | 37 MB | 14,5 MB | Menos nodos |
| Carga de `/radar`: primera tarjeta | 1 285 ms | 600 ms | Listado ligero |
| Bytes transferidos | 1 510 KB (listado 894 KB) | 768 KB (listado 134 KB) | Listado sin descripciones (`slim`); la descripción se pide al abrir la oferta (~0,4 s) |
| Recarga dentro de la sesión (interactivo) | 2 689 ms | 1 187 ms | La intro de arranque completa se ve una vez por sesión |
| Arrastre de la ventana: CPU del hilo principal | 521 ms/s | 93 ms/s | Con menos nodos y `transform` |
| Estirar el panel: fotograma máximo | 667 ms | 117 ms | Con menos nodos y un solo relayout al soltar |
| JS en reposo | 4,0 s libres de 5,2 s; el resto es render nativo | — | El coste no es JavaScript: es DOM, estilo y pintura |
| Bundle | `maplibre-gl` = 1,03 MB de ~2,6 MB | — | Motor de mapas WebGL |

Descartado tras medir: quitar el barrido CRT (`scanline`, `flicker`) o las animaciones de entrada de tarjetas no cambió el consumo en reposo;
no conviene "optimizar" eso sin evidencia.

## 2. Qué quitaría y qué haría, por capa

### Datos y servidor (mayor palanca)
| Acción | Efecto esperado | Estado |
|---|---|---|
| Índice `job_sources(job_id, last_seen_at)` y otros dos | 90× en listados | Hecho |
| Compresión gzip selectiva (sin tocar el chat) | 4× menos bytes | Hecho |
| Aplicar el esquema una vez por proceso | −1,7 ms por llamada | Hecho |
| No enviar `description` en los listados (`?slim=1`) y traerla con `/api/jobs/{id}/description` | −85 % del listado comprimido | Hecho |
| Paginación y filtros en servidor; el mapa recibe puntos agregados por lugar | Carga inicial constante aunque crezca la base | Pendiente |
| `Cache-Control`/ETag de 30 s en listados y en `/api/map/*` | Recargas instantáneas | Pendiente |
| Guardar el lugar (`place`, precisión) al ingestar en vez de calcularlo por petición | −1 pasada por oferta en cada consulta | Pendiente |
| `PRAGMA mmap_size`, `cache_size`, `temp_store=MEMORY` | Consultas más estables | Hecho (`ANALYZE` tras cada ingesta: pendiente) |

### Interfaz de escritorio
| Acción | Efecto esperado | Estado |
|---|---|---|
| Arrastre y estirado del agente sin relayout ni re-render | Ver medidas | Hecho |
| `content-visibility: auto` en tarjetas | Menos layout/pintura de lo que no se ve | Hecho |
| Lista de ofertas por tramos de 60 (incluye la oferta seleccionada para `j/k`) | De 52 000 a ~3 800 nodos al abrir | Hecho al abrir. **Medido de nuevo:** `useProgressiveList` solo crece (nunca desmonta lo que ya se mostró), así que tras recorrer toda la lista quedan 47 229 nodos (`node scripts/perf/measure.mjs scroll`), casi 6× el presupuesto. Pendiente: ventana deslizante real (desmontar tarjetas lejos del scroll). Las tarjetas tienen alto variable (sin altura fija), así que necesita una librería de virtualización o spacers medidos, no una franja fija; no se intentó esta vez por el riesgo de romper la selección con `j/k` sin poder probar cada modo (mapa, favoritos, ocultas) a fondo |
| Cargar `maplibre-gl` bajo demanda y no en la primera pintura | −1 MB en la carga inicial | **Hecho** (ya estaba, vía `next/dynamic`): medido con Chromium por CDP, el chunk se pide a los 207 ms, después de que el shell ya es interactivo (144 ms) y antes de que terminen de pintarse las tarjetas (411 ms); no bloquea nada. En la red pesa ~270 KB comprimido, no el ~1 MB sin comprimir que decía esta fila |
| Partir `RadarClient` en componentes con `memo` y estado local | Menos re-renders al filtrar | Parcial: `OfferSignalCard` y `JobCard` (las piezas caras, una por oferta) ya están con `memo`, y `visibleJobs` y los conteos derivados ya usan `useMemo`. El archivo en sí (880 líneas) sigue sin dividirse; sin una regresión medida que lo pida, no es la prioridad ahora |
| Intro de arranque completa solo la primera vez de la sesión (y no con «reducir movimiento») | −1,5 s en cada recarga | Hecho |
| Bajar el número de filtros CSS (`filter`, sombras con desenfoque) en superficies grandes | Menos coste de pintura | Pendiente, con medición previa |

### Agente y móvil
| Acción | Efecto esperado | Estado |
|---|---|---|
| `React.memo` en líneas y Markdown; propiedades estables | Escribir/arrastrar no re-analiza el historial | Hecho |
| Resumir contexto (`/compact`) y avisar al 70 % | Menos tokens y latencia por turno | Hecho (aviso manual); automático pendiente |
| Definiciones de herramientas: ~5 600 tokens por llamada (45 en el chat; crece con cada herramienta nueva); quitar del esquema el `default` que el modelo no usa | −5 % ya hecho (~5 340 tokens); agruparlas por intención y exponer solo las relevantes bajaría 30–40 % más, pero exige probarlo contra un proveedor real para no arriesgar la fiabilidad de las llamadas | Parcial: el ahorro mecánico está hecho; agrupar por intención sigue pendiente |
| Móvil: `/api/map/places` ya agrega por lugar; añadir caché del service worker de 60 s | Mapa instantáneo al volver | Pendiente |

## 3. Presupuesto de rendimiento (para no volver atrás)

| Métrica | Objetivo |
|---|---|
| Listados y feed de la API | < 150 ms con 5 000 ofertas |
| Bytes de la carga inicial de `/radar` | < 1 MB comprimidos |
| Elementos del DOM en `/radar` | < 8 000 |
| Arrastrar/estirar ventanas | ≤ 1 relayout por gesto y 0 tareas largas |
| Primera pintura útil de `/m` | < 1 s en 4G |

Se comprueban con `node scripts/perf/measure.mjs <load|idle|drag|pinresize|scroll|detail>` (Chromium por CDP: bytes, nodos, layout, tareas largas y fotogramas; necesita la API en `127.0.0.1:8101`) y con pruebas de la API que fallan si desaparece un índice o el modo `slim`.

## 4. Orden propuesto

1. ~~Quitar `description` de los listados y añadir el detalle bajo demanda~~ (hecho, junto con la lista por tramos y la intro por sesión).
2. Desmontar de verdad las tarjetas fuera de pantalla (ventana deslizante) y cargar el mapa bajo demanda.
3. Agregar puntos del mapa en el servidor y guardar el lugar al ingestar.
4. Caché HTTP condicional (ETag) y `ANALYZE` tras cada ingesta.
5. Reducir las definiciones de herramientas del agente.

Nota sobre el trabajo en `RadarClient.tsx`: los cambios de rendimiento de ese archivo (descripción bajo demanda y lista por tramos)
se commitearon **sobre la versión de `HEAD`**, sin tus cambios sin commitear de ese archivo, que siguen en tu copia de trabajo.
