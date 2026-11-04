"""Taxonomía y relevancia del mercado objetivo de la carrera activa.

La taxonomía no intenta decidir si una persona debe postular. Solo separa el
mercado capturado en capas para que la vista pueda priorizarlo sin borrar
ofertas ni depender de un modelo opaco.
"""

from __future__ import annotations

from dataclasses import dataclass

from radar.careers import CareerPack, default_pack
from radar.classification_text import contains, context_evidence, job_text
from radar.domain.models import RawJob
from radar.normalize import normalize_text


@dataclass(frozen=True, slots=True)
class Relevance:
    tier: str
    score: float
    evidence: str


def _tier_for_area(area: str | None, pack: CareerPack) -> str:
    area = pack.legacy_area_aliases.get(area, area)
    if area in pack.core_areas:
        return "core"
    if area in pack.adjacent_areas:
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
    sections = job_text(job.description)
    description = normalize_text(sections.role)
    areas = [area for area in [primary_area, *(secondary_areas or [])] if area]
    tier = _tier_for_area(primary_area, pack)

    excluded = next((phrase for phrase in pack.excluded_title_signals if contains(title, phrase)), None)
    if excluded:
        return Relevance("out_of_focus", 0.98, f"Título excluido: {excluded}")

    excluded_role = next((p for p in pack.excluded_role_signals if contains(description, p)), None)
    if excluded_role:
        return Relevance("out_of_focus", 0.9, f"Funciones fuera del mercado: {excluded_role}")
    rule = pack.area_evidence_rules.get(primary_area)
    if rule and not context_evidence(title, sections, rule):
        return Relevance("out_of_focus", 0.8, "Sin funciones o título suficientes para el área")

    operational = next((phrase for phrase in pack.operational_titles if contains(title, phrase)), None)
    if operational:
        return Relevance("out_of_focus", 0.9, f"Puesto operativo: {operational}")
    target = next((phrase for phrase in pack.target_titles if contains(title, phrase)), None)
    if target and tier == "core":
        return Relevance("core", 0.97, f"Cargo objetivo: {target}")
    secondary = next((phrase for phrase in pack.target_secondary_titles if contains(title, phrase)), None)
    if secondary and tier == "core":
        return Relevance("core", 0.92, f"Cargo objetivo (prioridad 2): {secondary}")

    area_evidence = ", ".join(areas) or "sin área suficiente"
    adjacent_title = next((phrase for phrase in pack.adjacent_title_signals if contains(title, phrase)), None)
    if adjacent_title and tier == "out_of_focus":
        return Relevance("adjacent", 0.7, f"Carrera en el título: {adjacent_title}")
    has_operational_context = any(
        contains(f"{title} {description}", phrase) for phrase in pack.context_terms
    )
    title_has_area = primary_area is not None and any(
        contains(title, token) for token in normalize_text(primary_area).split() if len(token) > 3
    )
    education_only = any(contains(description, phrase) and not contains(title, phrase) for phrase in pack.education_only)

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
