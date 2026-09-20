/** Bundled as a lazy chunk: FastAPI only serves /_next and /radar, so a public/ file would 404. */
export function loadDistrictGeoJson() {
  return import("./lima_distritos.json").then((module) => module.default as unknown as GeoJSON.FeatureCollection<GeoJSON.Polygon | GeoJSON.MultiPolygon, Record<string, unknown>>);
}

/** Stable key shared by job locations and district GeoJSON properties. */
export function districtKey(value: string | null | undefined): string | null {
  if (!value) return null;
  const normalized = value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[(),.]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return null;
  if (normalized === "huachipa") return "lurigancho";
  if (normalized === "ate vitarte") return "ate";
  return normalized;
}
