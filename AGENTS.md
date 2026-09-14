# Guía para agentes de Radar

## Contexto

Radar es una aplicación local de Career Intelligence para explorar ofertas de empleo en Lima.
La fuente de verdad es PostgreSQL; FastAPI expone la API y Next.js genera el frontend estático
que FastAPI sirve en `/radar`.

Antes de cambiar comportamiento, leer en este orden:

1. `README.md` para el flujo de instalación y uso.
2. `docs/architecture.md` para límites y responsabilidades.
3. `docs/operations.md` para launcher, ingesta y verificación.
4. `docs/troubleshooting.md` si el problema es de ejecución.

## Mapa del código

- `src/radar/api.py`: endpoints HTTP y montaje del frontend estático.
- `src/radar/db/`: conexión, repositorio y consultas PostgreSQL.
- `src/radar/classify.py`: áreas, seniority y competencias detectadas.
- `frontend/components/RadarClient.tsx`: estado, filtros, ofertas, popups y herramientas del mapa.
- `frontend/components/MapView.tsx`: mapa MapLibre, distritos, etiquetas y radar.
- `frontend/components/LeafletMapView.tsx`: fallback cuando no existe WebGL2.
- `frontend/app/globals.css`: layout, tema grafito, popups y scrolls.
- `frontend/lib/api.ts`: cliente HTTP del frontend.
- `frontend/out/`: export estático servido por FastAPI; se regenera con el build y se versiona.

## Contratos de interfaz actuales

- La pantalla principal es `/radar`, centrada por defecto en Lima/Callao y en la vista Distritos.
- El mapa ocupa el fondo completo; los controles son herramientas flotantes: Filtros, Radar y
  Competencias. No reintroducir barra superior, barra inferior ni controles de zoom del mapa.
- El diseño es monocromático: negro, grafito y grises. No añadir acentos verdes salvo una decisión
  explícita de producto.
- Distritos muestra etiquetas compactas `Distrito · cantidad`; evita círculos superpuestos.
- Radar requiere seleccionar un distrito y ofrece radios de 2, 5 y 10 km. Su selector puede abrirse
  hacia arriba y el panel queda flotante en la zona inferior derecha.
- Competencias conserva el mapa de ofertas: el popup lista skills demandadas y al seleccionar una
  filtra las ofertas y sus señales en el mapa. El detalle de una oferta permanece alineado a la
  derecha cuando se abre desde esa herramienta.
- Las ofertas se presentan en una bandeja flotante redimensionable desde el tirador superior y
  con scroll interno. Las tarjetas deben conservar una altura compacta aunque haya pocas ofertas.
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
- No usar un LLM para decidir silenciosamente scores, niveles de competencia o vigencia.
- Las migraciones de base de datos son incrementales; no borrar el volumen PostgreSQL para aplicar
  cambios.
