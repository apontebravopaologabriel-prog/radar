// MapLibre 6 carga su worker como un módulo aparte; con el export estático el empaquetador no lo resuelve y el mapa
// queda en blanco ("Worker failed to load"). Se copia a public/maplibre/ y MapView lo apunta con setWorkerUrl.
import { cpSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "node_modules", "maplibre-gl", "dist");
const target = join(root, "public", "maplibre");
mkdirSync(target, { recursive: true });
for (const file of readdirSync(dist)) {
  if (/^maplibre-gl-(worker|shared)\.mjs$/.test(file)) cpSync(join(dist, file), join(target, file));
}
