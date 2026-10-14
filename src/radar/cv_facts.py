"""Protección contra datos inventados: detecta en un texto propuesto hechos que no están en el CV real.

Es código, no un modelo. De un texto propuesto se extraen números, nombres propios (empresas, productos, instituciones) y skills
del paquete de carrera; todo lo que no aparezca en el texto permitido (la línea original y su contexto) queda marcado como
«dato nuevo no verificado». Recortar, reordenar o cambiar verbos no añade hechos y pasa sin marcas. Ver ``docs/design-cv-studio.md``.
"""

from __future__ import annotations

import re
from typing import Any

from radar.careers import active_pack
from radar.normalize import normalize_text

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_PROPER = re.compile(r"(?<![\w])([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ&+#.\-]*)")
_SENTENCE_START = re.compile(r"(?:^|[.!?:;]\s+|[•\-–]\s+)$")
_COMMON = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "con", "para", "por", "y", "o", "a", "al", "se", "su", "sus",
    "lo", "que", "como", "mas", "más", "sin", "sobre", "entre", "the", "and", "with", "for", "of", "to", "in", "an",
    "lideré", "desarrollé", "implementé", "diseñé", "gestioné", "analicé", "automaticé", "reduje", "aumenté", "coordiné",
    "realicé", "elaboré", "optimicé", "apoyé", "participé", "colaboré", "creé", "mejoré", "lidere", "desarrolle",
}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".").rstrip("0").rstrip(".") if "." in n.replace(",", ".") else n for n in _NUMBER.findall(text)}


def _proper_names(text: str) -> set[str]:
    """Palabras con mayúscula inicial que no abren una frase, y siglas (SQL, SAP): candidatas a nombres propios."""
    names: set[str] = set()
    for match in _PROPER.finditer(text):
        word = match.group(1).strip(".-")
        if len(word) < 2:
            continue
        starts_sentence = bool(_SENTENCE_START.search(text[: match.start()]))
        is_acronym = word.isupper() and len(word) >= 2
        key = normalize_text(word)
        if (starts_sentence and not is_acronym) or key in _COMMON:
            continue
        names.add(key)
    return names


def _skills_in(text: str) -> set[str]:
    norm = normalize_text(text)
    found = set()
    for name, aliases in active_pack().skill_aliases.items():
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", norm) for alias in aliases):
            found.add(name)
    return found


def new_facts(proposed: str, allowed: str) -> list[dict[str, str]]:
    """Hechos de ``proposed`` ausentes en ``allowed``. Vacío = no añade nada nuevo."""
    allowed_norm = normalize_text(allowed)
    allowed_words = set(re.findall(r"[\wñ&+#.\-]+", allowed_norm))
    allowed_numbers = _numbers(allowed)
    flags: list[dict[str, str]] = []
    for number in sorted(_numbers(proposed) - allowed_numbers):
        flags.append({"kind": "number", "value": number})
    for name in sorted(_proper_names(proposed)):
        if name not in allowed_words and name not in allowed_norm:
            flags.append({"kind": "name", "value": name})
    for skill in sorted(_skills_in(proposed) - _skills_in(allowed)):
        flags.append({"kind": "skill", "value": skill})
    skill_keys = {normalize_text(f["value"]) for f in flags if f["kind"] == "skill"}
    return [f for f in flags if f["kind"] != "name" or f["value"] not in skill_keys]  # una herramienta nueva se informa una sola vez


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def whole_profile_text(profile: dict[str, Any]) -> str:
    return " ".join(_strings(profile))
