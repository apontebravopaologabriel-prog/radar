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
    "Mantenimiento": ("mantenimiento", "confiabilidad", "reliability", "mantenimiento industrial"),
    "Operaciones": ("operaciones", "operations"),
    "Proyectos / PMO": ("proyectos", "pmo", "project management"),
    "Seguridad y Salud en el Trabajo": ("sst", "seguridad y salud", "sso", "osha"),
    "Finanzas / Control de gestión": ("costos", "control de gestion", "finanzas"),
}

# Commercial roles get their own category instead of being forced into an
# industrial area by generic words found in their descriptions.
COMMERCIAL_RULES: tuple[str, ...] = (
    "ventas", "venta", "vendedor", "comercial", "asesor comercial", "ejecutivo comercial",
    "coordinador comercial", "jefe de ventas", "supervisor de ventas",
    "responsable comercial", "account executive", "key account", "sales engineer",
    "sales", "sales manager", "promotor", "business development",
)

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
    # Explicit soft-skill language only; generic boilerplate is excluded.
    "Comunicación": ("comunicacion efectiva", "comunicacion asertiva", "comunicacion escrita", "comunicacion verbal", "habilidades de comunicacion", "comunicacion"),
    "Trabajo en equipo": ("trabajo en equipo", "trabajo colaborativo", "teamwork"),
    "Pensamiento analítico": ("pensamiento analitico", "capacidad analitica", "habilidad analitica"),
    "Resolución de problemas": ("resolucion de problemas", "solucion de problemas", "problem solving"),
    "Liderazgo": ("liderazgo", "leadership", "liderar equipos", "gestion de equipos"),
    "Adaptabilidad": ("adaptabilidad", "capacidad de adaptacion", "flexibilidad para adaptarse", "flexible y adaptable"),
    "Negociación": ("habilidades de negociacion", "capacidad de negociacion", "negociacion con proveedores", "negociacion"),
    "Proactividad": ("proactividad", "proactivo", "iniciativa"),
    "Atención al detalle": ("atencion al detalle", "orientacion al detalle", "detallista"),
    "Orientación al cliente": ("orientacion al cliente", "enfoque en el cliente", "servicio al cliente", "customer service", "customer focus"),
    "Toma de decisiones": ("toma de decisiones", "toma de decision", "decision making"),
    "Colaboración": ("colaboracion", "colaborativo", "collaboration"),
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


def _match(text: str, phrase: str) -> re.Match[str] | None:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text)


def _requirement_type(text: str, start: int) -> str:
    context = text[max(0, start - 120):start]
    if any(token in context for token in ("requisito", "requerido", "indispensable", "obligatorio", "must", "debe contar")):
        return "required"
    if any(token in context for token in ("deseable", "preferible", "plus", "valorado", "seria ideal")):
        return "preferred"
    return "unknown"


def classify(job: RawJob) -> ClassifiedJob:
    title = normalize_text(job.title)
    description = normalize_text(job.description)
    text = f"{title} {description}"
    matched: list[tuple[float, int, Evidence]] = []
    commercial_title = next((phrase for phrase in sorted(COMMERCIAL_RULES, key=len, reverse=True) if _contains(title, phrase)), None)
    commercial_text = commercial_title or next((phrase for phrase in sorted(COMMERCIAL_RULES, key=len, reverse=True) if _contains(description, phrase)), None)
    if commercial_text:
        weight = 4.0 if commercial_title else 0.5
        matched.append((weight + len(commercial_text) / 100, -1, Evidence("Ventas / Comercial", 0.94 if commercial_title else 0.55, _evidence(text, commercial_text))))
    for order, (area, phrases) in enumerate(AREA_RULES.items()):
        phrase = next((p for p in sorted(phrases, key=len, reverse=True) if _contains(text, p)), None)
        if phrase:
            weight = 2.0 if _contains(title, phrase) else 1.0
            if commercial_title and not _contains(title, phrase):
                weight -= 0.75
            matched.append((weight + len(phrase) / 100, order, Evidence(area, 0.82, _evidence(text, phrase))))
    if not matched:
        evidence = Evidence("Otras", 0.35, "No se encontró una señal suficiente en el texto")
        matched = [(0, 0, evidence)]
    matched.sort(key=lambda item: (-item[0], item[1]))
    skills: list[tuple[str, Evidence]] = []
    for skill, aliases in SKILL_ALIASES.items():
        match = next((candidate for candidate in (_match(text, phrase) for phrase in sorted(aliases, key=len, reverse=True)) if candidate), None)
        if match:
            phrase = match.group(0)
            skills.append((skill, Evidence(skill, 0.9, _evidence(text, phrase), _requirement_type(text, match.start()))))
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
