# Troubleshooting

## La base de datos no aparece o está vacía

Radar usa SQLite; se crea automáticamente en `~/.local/share/radar/radar.db` (o en `RADAR_DB_PATH`)
en la primera conexión, con el esquema completo de `src/radar/db/schema_sqlite.sql` ya poblado
(catálogo de áreas y skills incluido). Si el archivo existe pero faltan tablas o catálogo nuevos,
basta con volver a conectar: `_ensure_runtime_schema()` reaplica de forma aditiva lo que falte. Ver
[`docs/database.md`](database.md).

## Computrabajo no devuelve resultados

Usa una búsqueda más corta, confirma `location=Lima`, revisa Node.js/npm y comprueba que `npx mcp-computrabajo@latest` pueda iniciarse directamente.

## JobSpy no instala

Usa Python 3.11 o 3.12 y el entorno `.venv-jobspy`. La versión actual fija NumPy 1.26.3 y puede fallar en Python 3.14.

## JobSpy devuelve datos incompletos

Cada bolsa impone límites distintos. Salario, fecha, descripción o URL pueden faltar; Radar conserva `raw_payload` y representa ausencias como `NULL`.

## No aparecen recomendaciones

Configura el perfil con `radar profile`. Las recomendaciones dependen de `job_scores`, que se recalculan al guardarlo.

## Duplicados inesperados

V1 usa empresa, título y ubicación normalizados. Dos puestos distintos con esos campos pueden compartir fingerprint. Las apariciones de fuente se conservan y no se borran automáticamente.

## El mapa muestra un error de WebGL

MapLibre requiere WebGL2. El frontend lo detecta antes de inicializarlo y cambia
automáticamente a `LeafletMapView` cuando el navegador o la GPU no lo soportan. Recarga
`/radar`; si el problema continúa, revisa la consola del navegador y confirma que la API
responde en `http://127.0.0.1:8100/api/health`.

## Radar no abre como aplicación de Chromium

El launcher debe terminar ejecutando Chromium con `--app`, no `xdg-open`. Valida la entrada
y pruébala con:

```bash
desktop-file-validate ~/.local/share/applications/radar.desktop
gtk-launch radar
```

Si la ventana anterior quedó abierta en otro navegador, ciérrala y vuelve a iniciar Radar
desde el launcher. Los logs están en `/home/paolo/.local/state/radar/`.

El launcher actual no usa el servidor de Next.js: compila `frontend/out` cuando falta y FastAPI
sirve la interfaz junto con la API en el puerto 8100. Si la interfaz no carga, revisa
`/home/paolo/.local/state/radar/frontend.log` y confirma que `/radar` responde después de
`/api/health`.

## El explorador no muestra el contenido inferior

El sidebar tiene scroll propio. Si parece no actualizarse durante `npm run dev`, recarga la
página sin caché. En pantallas pequeñas, la lista de ofertas también tiene un scroll interno
independiente para conservar accesibles el ranking y el resto del explorador.

## La vista CVs muestra "La API respondió 404" o "Perfil real no cargado"

- **404 en `/api/cv/*`:** la API en el puerto 8100 corre código anterior. El launcher la reinicia solo si
  el código cambió; si la iniciaste por otro medio, reiníciala como indica `docs/operations.md`.
- **"Perfil real no cargado":** falta `cv_master.json` junto a la base de datos
  (`~/.local/share/radar/`, o el directorio de `RADAR_DB_PATH`). Sin `targets/*.json` la vista dice
  que no hay CVs objetivo.
- **Sin foto:** se espera `photo.jpg` o `photo.png` en ese mismo directorio.
- **`save_target_profile` devuelve `errors`:** el esquema exige `quote` o `reason` en ítems explícitos,
  `reason` en inferidos y en `cubierto`, y valores válidos de `origin`, `status` y `kind`.
