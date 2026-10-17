from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

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
    "sjl": ("San Juan de Lurigancho", -12.015, -76.995),
    "smp": ("San Martín de Porres", -11.989, -77.085),
    "sjm": ("San Juan de Miraflores", -12.162, -76.963),
    "ves": ("Villa El Salvador", -12.214, -76.943),
    "vmt": ("Villa María del Triunfo", -12.160, -76.940),
    "el agustino": ("El Agustino", -12.048, -77.000),
    "nana": ("Lurigancho-Chosica", -11.936, -76.700),
    "villa el salvador": ("Villa El Salvador", -12.214, -76.943),
    "villa maria del triunfo": ("Villa María del Triunfo", -12.160, -76.940),
}

LIMA_CENTER = LocationPoint(-12.046, -77.043, "Lima", "city", 0.55, "city-centroid")

# Ciudades del Perú (fuera de Lima Metropolitana): etiqueta, latitud, longitud, departamento y
# alias (distritos o nombres alternativos que se resuelven a la misma ciudad). Coordenadas de
# referencia del centro urbano, con precisión de ciudad (aproximada).
_CITIES: tuple[tuple[str, float, float, str, tuple[str, ...]], ...] = (
    ("Arequipa", -16.409, -71.537, "Arequipa", ("cercado de arequipa", "yanahuara", "cayma", "cerro colorado", "paucarpata", "sachaca", "jose luis bustamante")),
    ("Cusco", -13.532, -71.967, "Cusco", ("cuzco", "wanchaq", "san sebastian cusco")),
    ("Trujillo", -8.112, -79.029, "La Libertad", ("victor larco", "huanchaco", "la esperanza", "el porvenir")),
    ("Chiclayo", -6.771, -79.841, "Lambayeque", ("jose leonardo ortiz",)),
    ("Piura", -5.194, -80.633, "Piura", ("castilla", "catacaos")),
    ("Iquitos", -3.749, -73.253, "Loreto", ()),
    ("Huancayo", -12.065, -75.205, "Junín", ("el tambo", "chilca")),
    ("Tacna", -18.006, -70.246, "Tacna", ("alto de la alianza", "ciudad nueva")),
    ("Puno", -15.840, -70.022, "Puno", ()),
    ("Ica", -14.068, -75.729, "Ica", ()),
    ("Cajamarca", -7.157, -78.512, "Cajamarca", ("yanacocha",)),
    ("Pucallpa", -8.379, -74.554, "Ucayali", ("callería",)),
    ("Chimbote", -9.085, -78.578, "Áncash", ("nuevo chimbote",)),
    ("Ayacucho", -13.158, -74.224, "Ayacucho", ("huamanga",)),
    ("Huánuco", -9.930, -76.242, "Huánuco", ()),
    ("Tarapoto", -6.489, -76.365, "San Martín", ()),
    ("Juliaca", -15.500, -70.133, "Puno", ()),
    ("Talara", -4.577, -81.272, "Piura", ()),
    ("Sullana", -4.904, -80.685, "Piura", ()),
    ("Huaraz", -9.527, -77.528, "Áncash", ()),
    ("Tumbes", -3.567, -80.451, "Tumbes", ()),
    ("Moquegua", -17.194, -70.935, "Moquegua", ()),
    ("Ilo", -17.639, -71.338, "Moquegua", ()),
    ("Puerto Maldonado", -12.593, -69.189, "Madre de Dios", ()),
    ("Abancay", -13.637, -72.881, "Apurímac", ()),
    ("Cerro de Pasco", -10.687, -76.263, "Pasco", ("pasco",)),
    ("Huancavelica", -12.787, -74.977, "Huancavelica", ()),
    ("Chachapoyas", -6.229, -77.870, "Amazonas", ()),
    ("Moyobamba", -6.034, -76.972, "San Martín", ()),
    ("Jaén", -5.709, -78.807, "Cajamarca", ()),
    ("Paita", -5.089, -81.114, "Piura", ()),
    ("Sechura", -5.557, -80.822, "Piura", ()),
    ("Pisco", -13.710, -76.203, "Ica", ()),
    ("Chincha", -13.410, -76.132, "Ica", ("chincha alta",)),
    ("Nazca", -14.830, -74.939, "Ica", ("nasca",)),
    ("Marcona", -15.350, -75.160, "Ica", ("san juan de marcona",)),
    ("Cañete", -13.077, -76.386, "Lima", ("san vicente de canete", "imperial")),
    ("Huacho", -11.107, -77.605, "Lima", ("huaura",)),
    ("Huaral", -11.495, -77.208, "Lima", ()),
    ("Chancay", -11.564, -77.269, "Lima", ()),
    ("Barranca", -10.752, -77.761, "Lima", ()),
    ("Tingo María", -9.296, -75.994, "Huánuco", ()),
    ("Satipo", -11.253, -74.638, "Junín", ()),
    ("La Merced", -11.055, -75.327, "Junín", ("chanchamayo",)),
    ("Jauja", -11.776, -75.497, "Junín", ()),
    ("Tarma", -11.419, -75.690, "Junín", ()),
    ("La Oroya", -11.519, -75.900, "Junín", ()),
    ("Andahuaylas", -13.656, -73.387, "Apurímac", ()),
    ("Sicuani", -14.270, -71.226, "Cusco", ()),
    ("Quillabamba", -12.865, -72.694, "Cusco", ()),
    ("Mollendo", -17.023, -72.014, "Arequipa", ()),
    ("Camaná", -16.624, -72.711, "Arequipa", ()),
    ("Chepén", -7.225, -79.430, "La Libertad", ()),
    ("Pacasmayo", -7.401, -79.571, "La Libertad", ()),
    ("Casma", -9.474, -78.305, "Áncash", ()),
    ("Huarmey", -10.068, -78.153, "Áncash", ()),
    ("Lambayeque", -6.702, -79.906, "Lambayeque", ()),
    ("Ferreñafe", -6.638, -79.789, "Lambayeque", ()),
    ("Bagua Grande", -5.757, -78.442, "Amazonas", ("bagua",)),
    ("Yurimaguas", -5.900, -76.115, "Loreto", ()),
    ("Tocache", -8.185, -76.512, "San Martín", ()),
    ("Juanjuí", -7.179, -76.728, "San Martín", ()),
    ("Ilave", -16.083, -69.638, "Puno", ()),
)

# Departamentos (excepto Lima y Callao, que se resuelven aparte): capital como punto de referencia.
_DEPARTMENTS: tuple[tuple[str, float, float], ...] = (
    ("Amazonas", -6.229, -77.870), ("Áncash", -9.527, -77.528), ("Apurímac", -13.637, -72.881),
    ("Arequipa", -16.409, -71.537), ("Ayacucho", -13.158, -74.224), ("Cajamarca", -7.157, -78.512),
    ("Cusco", -13.532, -71.967), ("Huancavelica", -12.787, -74.977), ("Huánuco", -9.930, -76.242),
    ("Ica", -14.068, -75.729), ("Junín", -12.065, -75.205), ("La Libertad", -8.112, -79.029),
    ("Lambayeque", -6.771, -79.841), ("Loreto", -3.749, -73.253), ("Madre de Dios", -12.593, -69.189),
    ("Moquegua", -17.194, -70.935), ("Pasco", -10.687, -76.263), ("Piura", -5.194, -80.633),
    ("Puno", -15.840, -70.022), ("San Martín", -6.034, -76.972), ("Tacna", -18.006, -70.246),
    ("Tumbes", -3.567, -80.451), ("Ucayali", -8.379, -74.554),
)


def _build_index() -> tuple[
    list[tuple[re.Pattern[str], LocationPoint]],
    list[tuple[re.Pattern[str], LocationPoint]],
    list[tuple[re.Pattern[str], LocationPoint]],
]:
    def pattern(key: str) -> re.Pattern[str]:
        return re.compile(rf"(?<!\w){re.escape(normalize_text(key))}(?!\w)")

    cities: list[tuple[str, LocationPoint]] = []
    for label, lat, lon, _department, aliases in _CITIES:
        point = LocationPoint(lat, lon, label, "city", 0.6, "city-centroid")
        for key in (label, *aliases):
            cities.append((normalize_text(key), point))
    districts = [
        (normalize_text(district), LocationPoint(lat, lon, label, "district", 0.72, "district-centroid"))
        for district, (label, lat, lon) in LIMA_DISTRICTS.items()
    ]
    departments = [
        (normalize_text(name), LocationPoint(lat, lon, name, "department", 0.35, "department-capital"))
        for name, lat, lon in _DEPARTMENTS
    ]
    by_length = lambda item: -len(item[0])
    return (
        [(pattern(k), p) for k, p in sorted(cities, key=by_length)],
        [(pattern(k), p) for k, p in sorted(districts, key=by_length)],
        [(pattern(k), p) for k, p in sorted(departments, key=by_length)],
    )


_CITY_INDEX, _DISTRICT_INDEX, _DEPARTMENT_INDEX = _build_index()
_DESC_LOCATION_CLAUSE = re.compile(
    r"(?:lugar\s+de\s+trabajo|sede(?:\s+de\s+trabajo)?|ubicaci[oó]n|distrito|planta\s+en|almac[eé]n\s+en|oficinas?\s+en|laborar\s+en)\s*[:\-*]?\s*([^\n.;]{3,55})",
    re.IGNORECASE,
)


def place_catalog() -> dict[str, list[dict[str, object]]]:
    """Lugares elegibles como referencia: distritos de Lima/Callao y ciudades del resto del Perú."""
    districts = sorted({label for label, _, _ in LIMA_DISTRICTS.values()})
    return {
        "lima": [{"name": name, "kind": "district"} for name in districts],
        "peru": [
            {"name": label, "kind": "city", "department": department}
            for label, _lat, _lon, department, _aliases in sorted(_CITIES, key=lambda c: normalize_text(c[0]))
        ],
    }


@lru_cache(maxsize=8192)
def _resolve(normalized: str) -> LocationPoint | None:
    # 1) Ciudades fuera de Lima Metropolitana, por palabra completa: "Miraflores, Arequipa" es
    #    Arequipa, no el distrito limeño.
    for regex, point in _CITY_INDEX:
        if regex.search(normalized):
            return point
    # 2) Distritos de Lima y Callao, también por palabra completa ("estrategica" no es "Ate").
    for regex, point in _DISTRICT_INDEX:
        if regex.search(normalized):
            return point
    # 3) Solo el departamento: se ubica en su capital con precisión "department".
    for regex, point in _DEPARTMENT_INDEX:
        if regex.search(normalized):
            return point
    if re.search(r"(?<!\w)lima(?!\w)", normalized):
        return LIMA_CENTER
    return None  # "Perú" a secas no ubica la oferta en ningún punto


def infer_location(location: str | None) -> LocationPoint | None:
    """Resuelve una ubicación del Perú a distrito (Lima/Callao), ciudad o departamento."""
    normalized = normalize_text(location)
    return _resolve(normalized) if normalized else None


def infer_job_location(
    location: str | None,
    title: str | None = None,
    description: str | None = None,
) -> LocationPoint | None:
    """Resuelve la ubicación de una oferta; si el campo `location` es genérico ('Lima'), busca el distrito en título/descripción."""
    base = infer_location(location)
    if base is not None and (base.precision == "district" or base.label != "Lima"):
        return base
    if title:
        from_title = infer_location(title)
        if from_title is not None and from_title.precision == "district":
            return from_title
    if description:
        for match in _DESC_LOCATION_CLAUSE.finditer(description):
            from_desc = infer_location(match.group(1))
            if from_desc is not None and from_desc.precision == "district":
                return from_desc
    return base
