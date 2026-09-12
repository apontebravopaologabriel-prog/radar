# Troubleshooting

## PostgreSQL no responde

Revisa `docker compose ps` y `docker compose logs postgres --tail 100`. La URL por defecto es `postgresql://radar:radar_local_only@localhost:5433/radar`.

## Las tablas no aparecen

Los SQL de `/docker-entrypoint-initdb.d` se ejecutan solo cuando se crea el volumen. Para cambios posteriores usa una migración nueva.

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

El indicador `N` corresponde al modo desarrollo de Next.js. El launcher actual usa `npm run dev`
en el puerto 3000, por lo que puede aparecer. Para una distribución limpia como aplicación se
deberá cambiar el launcher a un flujo de producción con `npm run build` y `npm run start`.

## El explorador no muestra el contenido inferior

El sidebar tiene scroll propio. Si parece no actualizarse durante `npm run dev`, recarga la
página sin caché. En pantallas pequeñas, la lista de ofertas también tiene un scroll interno
independiente para conservar accesibles el ranking y el resto del explorador.
