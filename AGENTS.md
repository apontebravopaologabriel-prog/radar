# Guía para agentes de Radar

## Contexto

Radar es una aplicación local de Career Intelligence para explorar ofertas de empleo en Lima.
La fuente de verdad es SQLite (archivo local, sin servidor); FastAPI expone la API y Next.js genera
el frontend estático que FastAPI sirve en `/radar`.

Antes de cambiar comportamiento, leer en este orden:

1. `README.md` para el flujo de instalación y uso.
2. `docs/architecture.md` para límites y responsabilidades.
3. `docs/operations.md` para launcher, ingesta y verificación.
4. `docs/troubleshooting.md` si el problema es de ejecución.

## Mapa del código

- `src/radar/api.py`: endpoints HTTP y montaje del frontend estático.
- `src/radar/db/`: conexión, repositorio y consultas SQLite.
- `src/radar/cv_targets.py`: lectura de CVs objetivo hipotéticos (`docs/target-profiles.md`).
- `src/radar/cv_baseline.py`: brecha base determinista, ranking y combinación con el enriquecimiento.
- `src/radar/api_cv.py`: endpoints `/api/cv/*` (solo lectura).
- `frontend/components/CvView.tsx`: vista `CVs` (objetivos = favoritos ★, ranking, matriz, comparación, detalle); sus tipos y cliente están en `frontend/lib/cv-types.ts` y `cv-api.ts`, y sus estilos en `components/cv.css`.
- `src/radar/classify.py`: áreas, seniority y competencias detectadas.
- `frontend/components/RadarClient.tsx`: estado, filtros, ofertas, popups y herramientas del mapa.
- `frontend/components/MapView.tsx`: mapa MapLibre, distritos, etiquetas y radar.
- `frontend/components/LeafletMapView.tsx`: fallback cuando no existe WebGL2.
- `frontend/app/globals.css`: layout, tema grafito, popups y scrolls.
- `frontend/lib/api.ts`: cliente HTTP del frontend.
- `frontend/out/`: export estático servido por FastAPI; se regenera con el build y se versiona.

## Contratos de interfaz actuales

- La pantalla principal es `/radar`, centrada por defecto en Lima/Callao y en la vista Distritos.
- El mapa ocupa el fondo completo; los controles son herramientas flotantes: Filtros, Radar,
  Análisis y CVs. No reintroducir barra superior, barra inferior ni controles de zoom del mapa.
- El diseño es monocromático: negro, grafito y grises. No añadir acentos verdes salvo una decisión
  explícita de producto.
- El refresco automático consulta Indeed mediante JobSpy y Computrabajo mediante su adaptador MCP;
  cada portal debe ejecutarse de forma aislada para que un fallo no detenga la actualización.
- Distritos muestra etiquetas compactas `Distrito · cantidad`; evita círculos superpuestos.
- Radar requiere seleccionar un distrito y ofrece radios de 2, 5 y 10 km. Su selector puede abrirse
  hacia arriba y el panel queda flotante en la zona inferior derecha.
- Análisis y CVs reemplazan el mapa por su propia vista a pantalla completa (sin panel lateral). CVs
  deja libre el margen izquierdo para la barra de herramientas, marca todo CV objetivo como
  `HIPOTÉTICO — no enviar` y no ofrece exportarlo. Los objetivos son las ofertas con ★: no crear otro mecanismo de selección.
- Las ofertas se presentan en una bandeja flotante redimensionable desde el tirador superior y
  con scroll interno. Las tarjetas deben conservar una altura compacta aunque haya pocas ofertas.
  La bandeja también expone iconos compactos para alternar favoritos y ofertas ocultas.
- En cada señal, la fuente (`Indeed`, `LinkedIn`, etc.) aparece junto al área al pasar el mouse o
  enfocar la tarjeta; el título es el enlace directo a la oferta original y no debe abrir el detalle
  accidentalmente.
- La empresa puede mostrar un icono `⌖` discreto que abre una búsqueda externa de Google Maps con
  empresa + ubicación; no convertirlo en una integración de API ni dibujar sedes automáticamente
  en el mapa.
- El panel de filtros incluye selectores de portal (`Indeed`, `Computrabajo`, etc.) y competencia;
  ambos deben reutilizar los filtros de la API y mantener la selección sincronizada con el mapa.
- En el detalle, el botón de ocultar es únicamente un icono de ojo junto a la `X` de cierre. Al
  activarlo, el motivo aparece en un popup independiente a la izquierda del detalle; no volver a
  convertirlo en un formulario inline dentro de la tarjeta.
- Las descripciones se renderizan con el renderer Markdown local y no deben usar `dangerouslySetInnerHTML`
  con contenido de una fuente externa.

## Flujo de trabajo para cambios

1. Revisar `git status` y conservar cambios existentes que no pertenezcan a la tarea.
2. Editar código fuente; no editar manualmente `frontend/out`.
3. Para cambios visuales, ejecutar `cd frontend && npm run build` para regenerar el export.
4. Ejecutar `git diff --check`, `pytest` y `ruff check` cuando las dependencias estén instaladas.
5. Revisar el diff incluyendo los cambios generados en `frontend/out`.
6. Documentar cambios de comportamiento en `README.md` o en el documento específico de `docs/`.

## Comandos de verificación

```bash
cd /home/paolo/Projects/Radar
pytest
ruff check
git diff --check

cd frontend
npm run build
```

El build debe terminar con código 0 y sin warnings nuevos. Si Autoprefixer vuelve a señalar valores
de alineación, preferir la forma compatible `flex-start`/`flex-end`.

## Límites y seguridad

- No automatizar postulaciones, mensajes ni sesiones personales de portales.
- No borrar ofertas históricas ni modificar `jobs` para ocultar el estado personal; usar las tablas
  de estado/favoritos y sus endpoints.
- Mantener la inferencia de coordenadas como aproximada y no presentarla como ubicación exacta.
- Los CVs objetivo son hipotéticos: no presentarlos ni exportarlos como CV real. El perfil real, los
  CVs objetivo y la foto viven fuera del repositorio (`~/.local/share/radar/`); no versionarlos.
- No usar un LLM para decidir silenciosamente scores, niveles de competencia o vigencia.
- El esquema SQLite vive en `src/radar/db/schema_sqlite.sql`; un cambio de esquema se hace ahí (y en
  `_ensure_runtime_schema()` si debe aplicarse a bases ya creadas), no borrando el archivo `.db` ni
  añadiendo un `.sql` a `migrations/` (ese directorio es un artefacto histórico de PostgreSQL, ya no
  se ejecuta). Ver `docs/database.md`.
