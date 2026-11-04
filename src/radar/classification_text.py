"""Section-aware, deterministic evidence shared by all career packs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache, lru_cache

from radar.normalize import normalize_text

CLASSIFIER_VERSION = "2026-11-01.1"


@cache
def phrase_pattern(phrase: str, stem: bool = False) -> re.Pattern[str]:
    suffix = r"\w{0,8}" if stem else ""
    return re.compile(rf"(?<!\w){re.escape(normalize_text(phrase))}{suffix}(?!\w)")


def contains(text: str, phrase: str, *, stem: bool = False) -> bool:
    return bool(phrase_pattern(phrase, stem).search(text))


@cache
def _alternatives(phrases: tuple[str, ...], stem: bool = False) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(normalize_text(p)) for p in sorted(phrases, key=len, reverse=True))
    suffix = r"\w{0,8}" if stem else ""
    return re.compile(rf"(?<!\w)(?:{alternatives or '(?!)'}){suffix}(?!\w)")


@dataclass(frozen=True)
class JobText:
    role: str
    duties: tuple[str, ...]
    requirements: str


_HEADINGS = {
    "duties": (
        "funciones", "funciones principales", "principales funciones", "responsabilidades",
        "responsabilidades principales", "principales responsabilidades", "responsibilities",
        "cuales seran tus principales responsabilidades", "que lograras", "como lo lograras",
        "cual sera tu desafio", "objetivo del puesto", "mision del puesto",
        "la persona responsable estara a cargo de",
        "tus responsabilidades", "tus principales responsabilidades", "the role", "about the role",
        "what you'll do", "what you will do", "your responsibilities", "your role", "job description",
        "descripcion del puesto", "cuales seran tus principales funciones", "funciones del puesto",
    ),
    "requirements": (
        "requisitos", "requerimientos", "requisitos principales", "perfil", "qualifications",
        "requirements", "que buscamos", "que necesitamos de ti", "que te hara destacar",
        "conocimientos y herramientas", "deseables",
        "requisitos candidato/a", "que perfil buscamos", "what you bring", "what we're looking for",
    ),
    "ignore": (
        "empresa", "sobre nosotros", "acerca de nosotros", "about us", "beneficios",
        "que ofrecemos", "que te ofrecemos", "condiciones laborales", "ofrecemos",
        "quienes somos", "our benefits", "what we offer",
    ),
}


def _clean_heading(line: str) -> str:
    return normalize_text(re.sub(r"[*_#>¿?¡!📌✔️]", "", line)).strip(" .:-•\t")


@lru_cache(maxsize=128)
def job_text(description: str | None) -> JobText:
    """Retain job sections and discard explicit employer/benefits blocks.

    Unheaded text stays usable, but recognised requirements never count as duties.
    Blank lines are retained as clause boundaries even when a portal sends Markdown.
    """
    mode = "unknown"
    role, duties, requirements = [], [], []
    # Common HTML breaks must not join an employer block to a duties heading.
    text = re.sub(r"<\s*(?:br\s*/?|/p|/li|/div)\s*>", "\n", description or "", flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    for line in text.splitlines():
        clean = _clean_heading(line)
        if not clean:
            if mode == "intro":
                mode = "unknown"
            continue
        heading_mode = next((kind for kind, names in _HEADINGS.items()
                             if any(clean == name or clean.startswith(name + ":") for name in names)), None)
        if heading_mode:
            mode = heading_mode
            if ":" not in clean:
                continue
            clean = clean.split(":", 1)[1].strip()
            if not clean:
                continue
        if clean.startswith("about ") and heading_mode is None:
            mode = "ignore"
        # Company introductions without a heading cannot supply occupational evidence.
        if clean.startswith(("somos ", "nuestra empresa ", "empresa:", "about the company")):
            mode = "intro" if heading_mode is None else "ignore"
        if mode in {"ignore", "intro"}:
            continue
        role.append(clean)
        if mode == "requirements" or clean.startswith((
            "experiencia ", "conocimiento", "manejo de ", "dominio de ", "bachiller ",
            "egresado ", "formacion ", "requerimos ", "se requiere ", "dominio ",
            "experience ", "knowledge ", "proficiency ", "bachelor", "required ",
        )):
            requirements.append(clean)
        else:
            duties.extend(part.strip() for part in re.split(r"[;.!?]\s+", clean) if part.strip())
    return JobText("\n".join(role), tuple(duties), "\n".join(requirements))


def context_evidence(title: str, text: JobText, rule: dict) -> str | None:
    """Require a role title or an action and object in the same duty clause."""
    if _alternatives(tuple(rule.get("title_none", []))).search(title):
        return None
    if _alternatives(tuple(rule.get("title_any", []))).search(title):
        return title
    for clause in text.duties:
        if re.search(r"\b(?:no (?:se )?(?:realiz|desarroll|implement|requier)\w*|sin funciones de)\b", clause):
            continue
        for group in rule.get("duty_groups", []):
            actions = _alternatives(tuple(group["actions"]), True)
            objects = _alternatives(tuple(group["objects"]))
            for match in actions.finditer(clause):
                local = clause[match.start():match.end() + 160]
                for obj in objects.finditer(clause, match.end(), min(len(clause), match.end() + 160)):
                    gap = clause[match.end():obj.start()]
                    if not _alternatives(tuple(group.get("gap_excludes", []))).search(gap):
                        return local
    return None
