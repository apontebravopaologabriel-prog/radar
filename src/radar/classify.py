from __future__ import annotations

import re
from functools import cache

from radar.careers import CareerPack, default_pack
from radar.domain.models import ClassifiedJob, Evidence, RawJob
from radar.normalize import normalize_text


@cache
def _word(phrase: str, suffix: str = "", flags: int = 0) -> re.Pattern[str]:
    """Patrón compilado «palabra completa». El paquete tiene cientos de frases: sin esta memoización la caché de `re`
    (512 entradas) se desborda y casi todo el tiempo de clasificar se iba en recompilar (103 ms por oferta)."""
    return re.compile(rf"(?<!\w){re.escape(phrase)}{suffix}(?!\w)", flags)


def _evidence(text: str, phrase: str) -> str:
    match = _word(phrase, "", re.IGNORECASE).search(text)
    if not match:
        return phrase
    start = max(0, match.start() - 70)
    end = min(len(text), match.end() + 100)
    return text[start:end].strip()


def _contains(text: str, phrase: str) -> bool:
    return _word(phrase).search(text) is not None


def _match(text: str, phrase: str) -> re.Match[str] | None:
    return _word(phrase).search(text)


def _requirement_type(text: str, start: int) -> str:
    context = text[max(0, start - 120):start]
    if any(token in context for token in ("requisito", "requerido", "indispensable", "obligatorio", "must", "debe contar")):
        return "required"
    if any(token in context for token in ("deseable", "preferible", "plus", "valorado", "seria ideal")):
        return "preferred"
    return "unknown"


MIN_AREA_SCORE = 1.5  # un solo término débil o una mención suelta en la descripción no basta para asignar un área


def _title_contains(title: str, phrase: str) -> bool:
    """En el título se admiten derivados cortos («almacenero», «almacenes») para no depender de cada variante."""
    suffix = r"\w{0,5}" if len(phrase) >= 6 else ""  # las siglas cortas («bi», «sig») deben coincidir exactas
    return _word(phrase, suffix).search(title) is not None


def _area_score(title: str, description: str, phrases: tuple[str, ...], weak: frozenset[str]) -> tuple[float, str | None, bool]:
    """Puntaje acumulado de un área: título 3, menciones fuertes en la descripción 0.8 (máx. 3) y
    débiles 0.25 (máx. 2). Devuelve (puntaje, mejor frase, ¿hubo coincidencia en el título?)."""
    score, best, in_title = 0.0, None, False
    for phrase in sorted(phrases, key=len, reverse=True):
        if _title_contains(title, phrase):
            score += 3.0 + len(phrase) / 100
            best, in_title = best or phrase, True
            continue
        hits = len(_word(phrase).findall(description))
        if hits:
            score += (0.25 * min(hits, 2)) if phrase in weak else (0.8 * min(hits, 3))
            best = best or phrase
    return score, best, in_title


def classify(job: RawJob, pack: CareerPack | None = None) -> ClassifiedJob:
    pack = pack or default_pack()
    commercial_rules = tuple(p for rules in pack.out_of_focus_rules.values() for p in rules)
    commercial_area = next(iter(pack.out_of_focus_rules), None)
    title = normalize_text(job.title).replace("_", " ")
    description = normalize_text(job.description).replace("_", " ")
    text = f"{title} {description}"
    matched: list[tuple[float, int, Evidence]] = []
    commercial_title = next((phrase for phrase in sorted(commercial_rules, key=len, reverse=True) if _contains(title, phrase)), None)
    commercial_text = commercial_title or next((phrase for phrase in sorted(commercial_rules, key=len, reverse=True) if _contains(description, phrase)), None)
    if commercial_text and not commercial_title and len(_word(commercial_text).findall(description)) < 3:
        commercial_text = None  # una mención suelta en la descripción no vuelve comercial a una oferta
    if commercial_text and commercial_area:
        weight = 4.0 if commercial_title else 0.5
        matched.append((weight + len(commercial_text) / 100, -1, Evidence(commercial_area, 0.94 if commercial_title else 0.55, _evidence(text, commercial_text))))
    excluded_title = next((p for p in pack.excluded_title_signals if _contains(title, p)), None)
    any_title_hit = False
    for order, (area, phrases) in enumerate(pack.area_rules.items()):
        score, phrase, in_title = _area_score(title, description, phrases, pack.weak_terms)
        if not phrase or score < MIN_AREA_SCORE:
            continue
        if commercial_title and not in_title:
            score -= 0.75
        any_title_hit = any_title_hit or in_title
        matched.append((score, order, Evidence(area, min(0.92, 0.5 + score / 10), _evidence(text, phrase))))
    if excluded_title and not any_title_hit and not commercial_title:
        matched = [(0, 0, Evidence("Otras", 0.6, f"Título fuera del foco: {excluded_title}"))]
    if not matched:
        evidence = Evidence("Otras", 0.35, "No se encontró una señal suficiente en el texto")
        matched = [(0, 0, evidence)]
    matched.sort(key=lambda item: (-item[0], item[1]))
    skills: list[tuple[str, Evidence]] = []
    for skill, aliases in pack.skill_aliases.items():
        match = next((candidate for candidate in (_match(text, phrase) for phrase in sorted(aliases, key=len, reverse=True)) if candidate), None)
        if match:
            phrase = match.group(0)
            skills.append((skill, Evidence(skill, 0.9, _evidence(text, phrase), _requirement_type(text, match.start()))))
    evidences = [item[2] for item in matched]
    # Una oferta puede cruzar varias áreas del ISEBoK, pero limitarla a tres
    # mantiene el resultado interpretable y evita que cada palabra clave cree
    # una falsa lista de competencias.
    return ClassifiedJob(evidences[0], evidences[1:3], skills)


_INTERN_WORDS = ("practicante", "intern", "internship", "pasante", "becario", "trainee")
_SENIOR_WORDS = (
    "senior", "sr", "jefe", "gerente", "subgerente", "superintendente",
    "director", "coordinador", "lead", "lider", "head", "principal", "master",
)
_JUNIOR_WORDS = (
    "junior", "jr", "asistente", "auxiliar", "ayudante", "tecnico",
    "operario", "operador", "digitador", "almacenero", "estibador",
)
_MID_WORDS = (
    "analista", "especialista", "ingeniero", "planner", "planificador",
    "comprador", "encargado", "supervisor", "administrador", "gestor",
    "consultor", "auditor", "controller", "contador", "ejecutivo",
    "desarrollador", "programador", "arquitecto", "residente", "prevencionista",
    "inspector", "asesor", "analist", "specialist", "engineer", "analyst", "manager",
)


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(_word(w).search(text) is not None for w in words)


def infer_seniority(job: RawJob) -> str:
    title = normalize_text(job.title).replace("_", " ")
    desc = normalize_text(job.description or "").replace("_", " ")
    # 1. Evaluate title first so "Practicante ... reporta al Jefe" is not misclassified as senior.
    if _has_any(title, _INTERN_WORDS):
        return "intern"
    if _has_any(title, _SENIOR_WORDS):
        return "senior"
    if _has_any(title, _JUNIOR_WORDS):
        return "junior"
    if _has_any(title, _MID_WORDS):
        return "mid"
    # 2. Fallback to description cues when the title is generic.
    if any(p in desc for p in ("convenio de practicas", "practicante pre", "practicante profesional", "practicante", "internship")):
        return "intern"
    if any(p in desc for p in ("trainee", "programa trainee")):
        return "intern"
    if any(p in desc for p in ("recien egresado", "sin experiencia", "6 meses de experiencia", "1 ano de experiencia", "junior", "asistente")):
        return "junior"
    if any(p in desc for p in ("4 anos de experiencia", "5 anos de experiencia", "mas de 5 anos", "senior", "jefe", "gerente", "coordinador")):
        return "senior"
    if any(p in desc for p in ("2 anos de experiencia", "3 anos de experiencia", "2 a 3 anos", "analista", "especialista", "supervisor")):
        return "mid"
    return "unknown"
