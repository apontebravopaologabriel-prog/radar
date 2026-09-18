from __future__ import annotations

from dataclasses import dataclass

from radar.normalize import normalize_text


@dataclass(frozen=True, slots=True)
class LocationPoint:
    latitude: float
    longitude: float
    label: str
    precision: str
    confidence: float
    source: str


# Approximate district centroids. They are deliberately marked as district-level
# coordinates until an address geocoder is added to the ingestion pipeline.
LIMA_DISTRICTS: dict[str, tuple[str, float, float]] = {
    "ate": ("Ate", -12.025, -76.917),
    "santa clara": ("Ate", -12.025, -76.917),
    "barranco": ("Barranco", -12.149, -77.021),
    "brena": ("Breña", -12.058, -77.050),
    "callao": ("Callao", -12.056, -77.118),
    "cercado de lima": ("Cercado de Lima", -12.046, -77.043),
    "chorrillos": ("Chorrillos", -12.171, -77.018),
    "comas": ("Comas", -11.950, -77.058),
    "independencia": ("Independencia", -11.990, -77.045),
    "jesus maria": ("Jesús María", -12.078, -77.043),
    "la molina": ("La Molina", -12.080, -76.938),
    "la victoria": ("La Victoria", -12.072, -77.018),
    "la perla": ("La Perla", -12.071, -77.106),
    "punta hermosa": ("Punta Hermosa", -12.336, -76.822),
    "lince": ("Lince", -12.086, -77.030),
    "los olivos": ("Los Olivos", -11.982, -77.071),
    "magdalena del mar": ("Magdalena del Mar", -12.093, -77.076),
    "magdalena": ("Magdalena del Mar", -12.093, -77.076),
    "miraflores": ("Miraflores", -12.126, -77.031),
    "pueblo libre": ("Pueblo Libre", -12.077, -77.062),
    "puente piedra": ("Puente Piedra", -11.860, -77.076),
    "rimac": ("Rímac", -12.020, -77.030),
    "san borja": ("San Borja", -12.103, -76.998),
    "san isidro": ("San Isidro", -12.097, -77.037),
    "san juan de lurigancho": ("San Juan de Lurigancho", -12.015, -76.995),
    "san juan de miraflores": ("San Juan de Miraflores", -12.162, -76.963),
    "ciudad de dios": ("San Juan de Miraflores", -12.162, -76.963),
    "san luis": ("San Luis", -12.076, -76.998),
    "san miguel": ("San Miguel", -12.077, -77.093),
    "san martin de porres": ("San Martín de Porres", -11.989, -77.085),
    "san martin": ("San Martín de Porres", -11.989, -77.085),
    "santiago de surco": ("Santiago de Surco", -12.144, -76.995),
    "surco": ("Santiago de Surco", -12.144, -76.995),
    "surquillo": ("Surquillo", -12.115, -77.014),
    "carabayllo": ("Carabayllo", -11.855, -77.037),
    "chaclacayo": ("Chaclacayo", -11.982, -76.768),
    "huachipa": ("Huachipa", -12.015, -76.934),
    "lurigancho-chosica": ("Lurigancho-Chosica", -11.936, -76.700),
    "lurin": ("Lurín", -12.276, -76.869),
    "santa anita": ("Santa Anita", -12.043, -76.971),
    "ventanilla": ("Ventanilla", -11.875, -77.118),
    "vitarte": ("Ate", -12.025, -76.917),
    "campoy": ("San Juan de Lurigancho", -12.015, -76.995),
    "nana": ("Lurigancho-Chosica", -11.936, -76.700),
    "villa el salvador": ("Villa El Salvador", -12.214, -76.943),
    "villa maria del triunfo": ("Villa María del Triunfo", -12.160, -76.940),
}

LIMA_CENTER = LocationPoint(-12.046, -77.043, "Lima", "city", 0.55, "city-centroid")


def infer_location(location: str | None) -> LocationPoint | None:
    """Resolve a job location conservatively to a district or Lima centroid."""
    normalized = normalize_text(location)
    if not normalized:
        return None
    for district, (label, latitude, longitude) in sorted(
        LIMA_DISTRICTS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if district in normalized:
            return LocationPoint(latitude, longitude, label, "district", 0.72, "district-centroid")
    if "lima" in normalized or "peru" in normalized:
        return LIMA_CENTER
    return None
