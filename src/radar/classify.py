from __future__ import annotations

import re

from radar.careers import CareerPack, default_pack
from radar.domain.models import ClassifiedJob, Evidence, RawJob
from radar.normalize import normalize_text

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


def classify(job: RawJob, pack: CareerPack | None = None) -> ClassifiedJob:
    pack = pack or default_pack()
    commercial_rules = tuple(p for rules in pack.out_of_focus_rules.values() for p in rules)
    commercial_area = next(iter(pack.out_of_focus_rules), None)
    title = normalize_text(job.title)
    description = normalize_text(job.description)
    text = f"{title} {description}"
    matched: list[tuple[float, int, Evidence]] = []
    commercial_title = next((phrase for phrase in sorted(commercial_rules, key=len, reverse=True) if _contains(title, phrase)), None)
    commercial_text = commercial_title or next((phrase for phrase in sorted(commercial_rules, key=len, reverse=True) if _contains(description, phrase)), None)
    if commercial_text and commercial_area:
        weight = 4.0 if commercial_title else 0.5
        matched.append((weight + len(commercial_text) / 100, -1, Evidence(commercial_area, 0.94 if commercial_title else 0.55, _evidence(text, commercial_text))))
    for order, (area, phrases) in enumerate(pack.area_rules.items()):
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
    for skill, aliases in pack.skill_aliases.items():
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
