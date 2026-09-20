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
| DOM de `/radar` | 31 326 elementos (1 146 tarjetas × ~27 nodos) | igual (`content-visibility` omite layout de lo que no se ve) | Lista completa sin virtualizar |
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
| No enviar `description` completa en los listados (≈5 de los 6 MB) y traerla con `/api/jobs/{id}` | −80 % de bytes sin gzip | Pendiente (toca `RadarClient.tsx`) |
| Paginación y filtros en servidor; el mapa recibe puntos agregados por lugar | Carga inicial constante aunque crezca la base | Pendiente |
| `Cache-Control`/ETag de 30 s en listados y en `/api/map/*` | Recargas instantáneas | Pendiente |
| Guardar el lugar (`place`, precisión) al ingestar en vez de calcularlo por petición | −1 pasada por oferta en cada consulta | Pendiente |
| `PRAGMA mmap_size`, `cache_size`, `temp_store=MEMORY` y `ANALYZE` tras cada ingesta | Consultas más estables | Pendiente |

### Interfaz de escritorio
| Acción | Efecto esperado | Estado |
|---|---|---|
| Arrastre y estirado del agente sin relayout ni re-render | Ver medidas | Hecho |
| `content-visibility: auto` en tarjetas | Menos layout/pintura de lo que no se ve | Hecho |
| Virtualizar la lista de ofertas (ventana de ~30 tarjetas) | De 31 000 a ~3 000 nodos | Pendiente (`RadarClient.tsx`) |
| Cargar `maplibre-gl` bajo demanda y no en la primera pintura | −1 MB en la carga inicial | Pendiente |
| Partir `RadarClient` en componentes con `memo` y estado local | Menos re-renders al filtrar | Pendiente |
| Pantalla de arranque: mostrarla solo si la carga supera 400 ms | Sensación de inmediatez | Pendiente |
| Bajar el número de filtros CSS (`filter`, sombras con desenfoque) en superficies grandes | Menos coste de pintura | Pendiente, con medición previa |

### Agente y móvil
| Acción | Efecto esperado | Estado |
|---|---|---|
| `React.memo` en líneas y Markdown; propiedades estables | Escribir/arrastrar no re-analiza el historial | Hecho |
| Resumir contexto (`/compact`) y avisar al 70 % | Menos tokens y latencia por turno | Hecho (aviso manual); automático pendiente |
| Definiciones de herramientas: ~2 700 tokens por llamada; agruparlas por intención y exponer solo las relevantes | −30–40 % de prompt por turno | Pendiente |
| Móvil: `/api/map/places` ya agrega por lugar; añadir caché del service worker de 60 s | Mapa instantáneo al volver | Pendiente |

## 3. Presupuesto de rendimiento (para no volver atrás)

| Métrica | Objetivo |
|---|---|
| Listados y feed de la API | < 150 ms con 5 000 ofertas |
| Bytes de la carga inicial de `/radar` | < 1 MB comprimidos |
| Elementos del DOM en `/radar` | < 8 000 |
| Arrastrar/estirar ventanas | ≤ 1 relayout por gesto y 0 tareas largas |
| Primera pintura útil de `/m` | < 1 s en 4G |

Se comprueban con `scripts/` de medición (Chromium por CDP: métricas de layout, tareas largas y fotogramas) y con pruebas de la API que fallan si desaparece un índice.

## 4. Orden propuesto

1. Quitar `description` de los listados y añadir el detalle bajo demanda (necesita coordinar con `RadarClient.tsx`, hoy con cambios sin commitear).
2. Virtualizar la lista y cargar el mapa bajo demanda.
3. Agregar puntos del mapa en el servidor y guardar el lugar al ingestar.
4. Caché HTTP y `PRAGMA`s.
5. Reducir las definiciones de herramientas del agente.
