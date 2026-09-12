from __future__ import annotations

import re

from radar.domain.models import ClassifiedJob, Evidence, RawJob
from radar.normalize import normalize_text

AREA_RULES: dict[str, tuple[str, ...]] = {
    "Supply Chain": ("supply chain", "cadena de suministro", "abastecimiento"),
    "Logística": ("logistica", "almacen", "warehouse", "distribucion"),
    "Compras": ("compras", "procurement", "buyer", "adquisiciones"),
    "Demand Planning": ("demand planning", "forecast", "pronostico", "s&op"),
    "Planeamiento": ("planeamiento", "planificacion", "planning"),
    "Mejora continua": ("mejora continua", "lean", "kaizen", "six sigma"),
    "Calidad": ("calidad", "quality", "iso 9001"),
    "Data / BI": ("power bi", "business intelligence", "data analyst", "analitica"),
    "Analytics": ("analytics", "analisis de datos", "machine learning"),
    "Automatización": ("automatizacion", "rpa", "power automate"),
    "Procesos": ("procesos", "process improvement", "bpmn"),
    "Producción": ("produccion", "manufactura", "planta"),
    "Operaciones": ("operaciones", "operations"),
    "Proyectos / PMO": ("proyectos", "pmo", "project management"),
    "Seguridad y Salud en el Trabajo": ("sst", "seguridad y salud", "sso", "osha"),
    "Finanzas / Control de gestión": ("costos", "control de gestion", "finanzas"),
}

SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "Excel": ("excel", "microsoft 365"),
    "Power BI": ("power bi",),
    "SQL": ("sql",),
    "Python": ("python",),
    "PostgreSQL": ("postgresql", "postgres"),
    "SAP": ("sap",),
    "Lean": ("lean",),
    "Six Sigma": ("six sigma", "six-sigma"),
    "Kaizen": ("kaizen",),
    "VSM": ("vsm", "value stream mapping"),
    "5S": ("5s",),
    "BPMN": ("bpmn",),
    "RPA": ("rpa",),
    "Power Automate": ("power automate",),
    "Tableau": ("tableau",),
    "Forecasting": ("forecasting", "forecast", "pronostico"),
    "Optimization": ("optimization", "optimizacion"),
    "OR-Tools": ("or-tools", "ortools"),
    "Supply Chain": ("supply chain",),
    "Inventory Management": ("inventario", "inventory management"),
    "S&OP": ("s&op", "sop"),
    "Demand Planning": ("demand planning",),
    "Project Management": ("project management", "gestion de proyectos"),
    "Scrum": ("scrum",),
    "English": ("ingles", "english"),
}


def _evidence(text: str, phrase: str) -> str:
    match = re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, flags=re.IGNORECASE)
    if not match:
        return phrase
    start = max(0, match.start() - 70)
    end = min(len(text), match.end() + 100)
    return text[start:end].strip()


def _contains(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def classify(job: RawJob) -> ClassifiedJob:
    title = normalize_text(job.title)
    description = normalize_text(job.description)
    text = f"{title} {description}"
    matched: list[tuple[float, int, Evidence]] = []
    for order, (area, phrases) in enumerate(AREA_RULES.items()):
        phrase = next((p for p in sorted(phrases, key=len, reverse=True) if _contains(text, p)), None)
        if phrase:
            weight = 2.0 if _contains(title, phrase) else 1.0
            matched.append((weight + len(phrase) / 100, order, Evidence(area, 0.82, _evidence(text, phrase))))
    if not matched:
        evidence = Evidence("Otras", 0.35, "No se encontró una señal suficiente en el texto")
        matched = [(0, 0, evidence)]
    matched.sort(key=lambda item: (-item[0], item[1]))
    skills: list[tuple[str, Evidence]] = []
    for skill, aliases in SKILL_ALIASES.items():
        phrase = next((p for p in sorted(aliases, key=len, reverse=True) if _contains(text, p)), None)
        if phrase:
            req = (
                "required"
                if any(
                    x in text[max(0, text.find(phrase) - 45) : text.find(phrase)]
                    for x in ("requerido", "required", "indispensable", "must")
                )
                else "unknown"
            )
            skills.append((skill, Evidence(skill, 0.9, _evidence(text, phrase), req)))
    evidences = [item[2] for item in matched]
    return ClassifiedJob(evidences[0], evidences[1:], skills)


def infer_seniority(job: RawJob) -> str:
    text = normalize_text(f"{job.title} {job.description or ''}")
    if any(x in text for x in ("practicante pre", "practicante", "intern", "internship")):
        return "intern"
    if any(x in text for x in ("trainee", "programa trainee")):
        return "trainee"
    if any(x in text for x in ("junior", "juniors", "asistente")):
        return "junior"
    if any(x in text for x in ("senior", "jefe", "gerente", "coordinador")):
        return "senior_or_lead"
    return "unknown"
