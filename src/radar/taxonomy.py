"""Taxonomía y relevancia del mercado objetivo de Ingeniería Industrial.

La taxonomía no intenta decidir si una persona debe postular. Solo separa el
mercado capturado en capas para que la vista pueda priorizarlo sin borrar
ofertas ni depender de un modelo opaco.
"""

from __future__ import annotations

from dataclasses import dataclass

from radar.domain.models import RawJob
from radar.normalize import normalize_text

CORE_AREAS = frozenset(
    {
        "Procesos",
        "Operaciones",
        "Mejora continua",
        "Producción",
        "Supply Chain",
        "Logística",
        "Compras",
        "Planeamiento",
        "Demand Planning",
        "Calidad",
        "Automatización",
        "Mantenimiento",
    }
)

ADJACENT_AREAS = frozenset(
    {
        "Data / BI",
        "Analytics",
        "Proyectos / PMO",
        "Finanzas / Control de gestión",
        "Seguridad y Salud en el Trabajo",
        "Recursos Humanos / People Analytics",
    }
)

OUT_OF_FOCUS_AREAS = frozenset({"Ventas / Comercial", "Otras"})

# La frase puede aparecer como requisito académico sin describir el puesto.
EDUCATION_ONLY = ("ingenieria industrial", "ingeniero industrial", "ing industrial")

EXCLUDED_TITLE_SIGNALS = (
    "auxiliar de limpieza",
    "operario de limpieza",
    "personal de limpieza",
    "asesor comercial",
    "ejecutivo comercial",
    "vendedor",
    "promotor de ventas",
    "televentas",
    "atencion al cliente",
)


@dataclass(frozen=True, slots=True)
class Relevance:
    tier: str
    score: float
    evidence: str


def _tier_for_area(area: str | None) -> str:
    if area in CORE_AREAS:
        return "core"
    if area in ADJACENT_AREAS:
        return "adjacent"
    return "out_of_focus"


def infer_relevance(job: RawJob, primary_area: str | None) -> Relevance:
    """Clasifica la cercanía al foco sin usar salario ni inventar campos.

    Las señales del título pesan más que las menciones educativas de la
    descripción. Una oferta comercial o de limpieza no se vuelve industrial
    solo porque mencione Ingeniería Industrial entre sus requisitos.
    """
    title = normalize_text(job.title)
    description = normalize_text(job.description or "")
    tier = _tier_for_area(primary_area)

    excluded = next((phrase for phrase in EXCLUDED_TITLE_SIGNALS if phrase in title), None)
    if excluded:
        return Relevance("out_of_focus", 0.98, f"Título excluido: {excluded}")

    area_evidence = primary_area or "sin área suficiente"
    has_operational_context = any(
        phrase in f"{title} {description}"
        for phrase in (
            "proceso", "operacion", "logistica", "supply chain", "compras",
            "planeamiento", "produccion", "calidad", "lean", "six sigma",
            "automatizacion", "rpa", "power bi", "analitica", "proyecto",
            "inventario", "almacen", "mejora continua", "manufactura",
        )
    )
    title_has_area = primary_area is not None and any(
        token in title for token in normalize_text(primary_area).split() if len(token) > 3
    )
    education_only = any(phrase in description and phrase not in title for phrase in EDUCATION_ONLY)

    if tier == "core":
        if title_has_area or has_operational_context:
            score = 0.95 if title_has_area else 0.84
            return Relevance("core", score, f"Área núcleo: {area_evidence}")
        if education_only:
            return Relevance("adjacent", 0.52, "Ingeniería Industrial aparece como requisito, sin señal operativa suficiente")
        return Relevance("core", 0.68, f"Área núcleo con evidencia limitada: {area_evidence}")

    if tier == "adjacent":
        score = 0.78 if title_has_area or has_operational_context else 0.62
        return Relevance("adjacent", score, f"Área adyacente: {area_evidence}")

    return Relevance("out_of_focus", 0.78 if primary_area else 0.45, f"Fuera del foco inicial: {area_evidence}")
