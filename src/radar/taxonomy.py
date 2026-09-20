"""Taxonomía y relevancia del mercado objetivo de la carrera activa.

La taxonomía no intenta decidir si una persona debe postular. Solo separa el
mercado capturado en capas para que la vista pueda priorizarlo sin borrar
ofertas ni depender de un modelo opaco.
"""

from __future__ import annotations

from dataclasses import dataclass

from radar.careers import CareerPack, default_pack
from radar.domain.models import RawJob
from radar.normalize import normalize_text


@dataclass(frozen=True, slots=True)
class Relevance:
    tier: str
    score: float
    evidence: str


_LEGACY_CORE_AREAS = frozenset({
    "Automatización", "Calidad", "Compras", "Demand Planning", "Logística", "Mantenimiento",
    "Mejora continua", "Operaciones", "Planeamiento", "Procesos", "Producción", "Supply Chain",
})
_LEGACY_ADJACENT_AREAS = frozenset({
    "Analytics", "Data / BI", "Finanzas / Control de gestión", "Proyectos / PMO",
    "Recursos Humanos / People Analytics", "Seguridad y Salud en el Trabajo",
})


def _tier_for_area(area: str | None, pack: CareerPack) -> str:
    if area in pack.core_areas:
        return "core"
    if area in pack.adjacent_areas:
        return "adjacent"
    # Compatibility for callers/tests that still pass a pre-ISEBoK label.
    if area in _LEGACY_CORE_AREAS:
        return "core"
    if area in _LEGACY_ADJACENT_AREAS:
        return "adjacent"
    return "out_of_focus"


def infer_relevance(
    job: RawJob,
    primary_area: str | None,
    pack: CareerPack | None = None,
    secondary_areas: list[str] | None = None,
) -> Relevance:
    """Clasifica la cercanía al foco sin usar salario ni inventar campos.

    Las señales del título pesan más que las menciones educativas de la
    descripción. Una oferta comercial o de limpieza no se vuelve industrial
    solo porque mencione Ingeniería Industrial entre sus requisitos.
    """
    pack = pack or default_pack()
    title = normalize_text(job.title)
    description = normalize_text(job.description or "")
    areas = [area for area in [primary_area, *(secondary_areas or [])] if area]
    tiers = [_tier_for_area(area, pack) for area in areas]
    tier = "core" if "core" in tiers else "adjacent" if "adjacent" in tiers else "out_of_focus"

    excluded = next((phrase for phrase in pack.excluded_title_signals if phrase in title), None)
    if excluded:
        return Relevance("out_of_focus", 0.98, f"Título excluido: {excluded}")

    area_evidence = ", ".join(areas) or "sin área suficiente"
    has_operational_context = any(
        phrase in f"{title} {description}" for phrase in pack.context_terms
    )
    title_has_area = primary_area is not None and any(
        token in title for token in normalize_text(primary_area).split() if len(token) > 3
    )
    education_only = any(phrase in description and phrase not in title for phrase in pack.education_only)

    if tier == "core":
        if title_has_area or has_operational_context:
            score = 0.95 if title_has_area else 0.84
            return Relevance("core", score, f"Área núcleo: {area_evidence}")
        if education_only:
            return Relevance("adjacent", 0.52, "La carrera aparece como requisito, sin señal operativa suficiente")
        return Relevance("core", 0.68, f"Área núcleo con evidencia limitada: {area_evidence}")

    if tier == "adjacent":
        score = 0.78 if title_has_area or has_operational_context else 0.62
        return Relevance("adjacent", score, f"Área adyacente: {area_evidence}")

    return Relevance("out_of_focus", 0.78 if primary_area else 0.45, f"Fuera del foco inicial: {area_evidence}")
