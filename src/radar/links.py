"""Enlaces externos deterministas que Radar puede mostrar al usuario."""

from urllib.parse import quote


def google_maps_search_url(company: str | None, location: str | None = None) -> str | None:
    """Construye una búsqueda de Google Maps para una empresa y su ubicación aproximada."""
    name = (company or "").strip()
    if not name:
        return None
    place = (location or "Lima").strip()
    query = ", ".join(part for part in (name, place, "Perú") if part)
    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"
