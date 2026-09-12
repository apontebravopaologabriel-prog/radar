export const DISTRICT_GEOJSON_URL =
  "https://raw.githubusercontent.com/joseluisq/peru-geojson-datasets/master/lima_callao_distritos_simple.geojson";

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
