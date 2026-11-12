# Archived: mobile PWA (`/m`)

The experimental mobile interface (Today feed, Map, Pipeline, Agent, service worker) was removed from the active
project. It is kept here for reference only; it is not built, linted or served, and its relative imports no longer
resolve. The shared settings/onboarding components that the desktop still uses live in `frontend/components/settings/`.

To restore it, move `app/m/` and `components/*` back into `frontend/` (components under `frontend/components/mobile/`),
`public/sw.js` into `frontend/public/`, and re-add the `/m` and `sw.js` routes in `src/radar/api.py`.
