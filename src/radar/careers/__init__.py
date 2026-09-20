"""Paquetes de carrera: la taxonomía y el scoring como datos, no como código.

Cada paquete (`packs/*.json`) define áreas, señales, competencias y pesos de una carrera.
Añadir una carrera nueva es añadir un JSON; el motor de clasificación es el mismo.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from radar.normalize import normalize_text

PACKS_DIR = Path(__file__).resolve().parent / "packs"
DEFAULT_CAREER = "industrial_engineering"
WEIGHT_KEYS = ("area", "skills", "seniority", "education", "location", "preference")


class CareerPackError(ValueError):
    """El paquete no existe o no cumple el formato mínimo."""


@dataclass(frozen=True, slots=True)
class SkillDef:
    name: str
    aliases: tuple[str, ...]
    category: str | None
    type: str


@dataclass(frozen=True, slots=True)
class CareerPack:
    id: str
    name: str
    country: str
    language: str
    core_areas: frozenset[str]
    adjacent_areas: frozenset[str]
    out_of_focus_areas: frozenset[str]
    area_slugs: dict[str, str]
    area_rules: dict[str, tuple[str, ...]]
    out_of_focus_rules: dict[str, tuple[str, ...]]
    skills: dict[str, SkillDef]
    excluded_title_signals: tuple[str, ...]
    education_only: tuple[str, ...]
    context_terms: tuple[str, ...]
    weights: dict[str, float]
    queries: tuple[str, ...] = field(default_factory=tuple)
    weak_terms: frozenset[str] = frozenset()  # genéricas: solo puntúan fuertes en el título

    @property
    def skill_aliases(self) -> dict[str, tuple[str, ...]]:
        return {n: s.aliases for n, s in self.skills.items() if s.aliases}

    @property
    def all_areas(self) -> list[str]:
        return sorted(self.core_areas | self.adjacent_areas | self.out_of_focus_areas)


def _validate(raw: dict, source: str) -> None:
    for key in ("id", "name", "areas", "area_rules", "skills", "scoring"):
        if key not in raw:
            raise CareerPackError(f"{source}: falta '{key}'")
    weights = raw["scoring"]
    if set(weights) != set(WEIGHT_KEYS):
        raise CareerPackError(f"{source}: scoring debe tener exactamente {WEIGHT_KEYS}")
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise CareerPackError(f"{source}: los pesos deben sumar 1")
    known = set(raw["areas"].get("core", [])) | set(raw["areas"].get("adjacent", [])) | set(
        raw["areas"].get("out_of_focus", [])
    )
    unknown = (set(raw["area_rules"]) | set(raw.get("out_of_focus_rules", {}))) - known
    if unknown:
        raise CareerPackError(f"{source}: reglas para áreas no declaradas: {sorted(unknown)}")


def parse_pack(raw: dict, source: str = "pack") -> CareerPack:
    _validate(raw, source)
    areas = raw["areas"]
    return CareerPack(
        id=raw["id"],
        name=raw["name"],
        country=raw.get("country", "PE"),
        language=raw.get("language", "es"),
        core_areas=frozenset(areas.get("core", [])),
        adjacent_areas=frozenset(areas.get("adjacent", [])),
        out_of_focus_areas=frozenset(areas.get("out_of_focus", [])),
        area_slugs=dict(raw.get("area_slugs", {})),
        area_rules={k: tuple(v) for k, v in raw["area_rules"].items()},
        out_of_focus_rules={k: tuple(v) for k, v in raw.get("out_of_focus_rules", {}).items()},
        skills={
            n: SkillDef(n, tuple(s.get("aliases", [])), s.get("category"), s.get("type", "technical"))
            for n, s in raw["skills"].items()
        },
        excluded_title_signals=tuple(raw.get("excluded_title_signals", [])),
        education_only=tuple(raw.get("education_only", [])),
        context_terms=tuple(raw.get("context_terms", [])),
        weights=dict(raw["scoring"]),
        queries=tuple(raw.get("queries", [])),
        weak_terms=frozenset(normalize_text(t) for t in raw.get("weak_terms", [])),
    )


def user_packs_dir() -> Path:
    """Carreras creadas por el usuario: viven junto a su base de datos (cada persona, su equipo)."""
    from radar.db.database import database_path

    return database_path().parent / "careers"


@cache
def _load(career_id: str, user_dir: str) -> CareerPack:
    for directory in (PACKS_DIR, Path(user_dir)):
        path = directory / f"{career_id}.json"
        if path.is_file() and path.resolve().parent == directory.resolve():
            return parse_pack(json.loads(path.read_text(encoding="utf-8")), path.name)
    raise CareerPackError(f"Carrera desconocida: {career_id}")


def load_pack(career_id: str) -> CareerPack:
    return _load(career_id, str(user_packs_dir()))


def list_packs() -> list[CareerPack]:
    ids = {p.stem for p in PACKS_DIR.glob("*.json")}
    user_dir = user_packs_dir()
    if user_dir.is_dir():
        ids |= {p.stem for p in user_dir.glob("*.json")}
    packs = []
    for career_id in sorted(ids):
        try:
            packs.append(load_pack(career_id))
        except (CareerPackError, ValueError):  # un JSON de usuario dañado no debe romper la app
            continue
    return packs


MAX_AREAS = 20
MAX_SKILLS = 60
MAX_KEYWORDS = 12
DEFAULT_WEIGHTS = {"area": 0.30, "skills": 0.25, "seniority": 0.15, "education": 0.10, "location": 0.10, "preference": 0.10}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_text(value)).strip("-")


def _clean(value: str, limit: int = 60) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def save_custom_pack(
    name: str,
    areas: dict[str, list[str]],
    skills: list[str] | None = None,
    queries: list[str] | None = None,
) -> CareerPack:
    """Crea (o reemplaza) una carrera propia a partir de áreas con palabras clave y una lista de skills.

    Es determinista: sin modelo de lenguaje. Cada área se reconoce por sus palabras clave y cada skill
    por su nombre. Devuelve el paquete ya validado y guardado junto a la base del usuario.
    """
    name = _clean(name, 80)
    if not name:
        raise CareerPackError("La carrera necesita un nombre")
    areas = {_clean(k): v for k, v in areas.items() if _clean(k)}
    if not areas or len(areas) > MAX_AREAS:
        raise CareerPackError(f"Indica entre 1 y {MAX_AREAS} áreas")
    skill_names = list(dict.fromkeys(_clean(x) for x in (skills or []) if _clean(x)))
    if len(skill_names) > MAX_SKILLS:
        raise CareerPackError(f"Máximo {MAX_SKILLS} skills")
    slug = _slug(name)
    if not slug:
        raise CareerPackError("Nombre de carrera inválido")
    area_rules = {}
    for area, keywords in areas.items():
        terms = [normalize_text(t) for t in [area, *keywords] if normalize_text(_clean(t))]
        area_rules[area] = list(dict.fromkeys(terms))[: MAX_KEYWORDS + 1]
    raw = {
        "id": f"custom_{slug}"[:48],
        "name": name,
        "country": "PE",
        "language": "es",
        "areas": {"core": list(areas), "adjacent": [], "out_of_focus": ["Otras"]},
        "area_slugs": {**{a: _slug(a) or "area" for a in areas}, "Otras": "otras"},
        "area_rules": area_rules,
        "out_of_focus_rules": {},
        "skills": {
            n: {"aliases": [normalize_text(n)], "category": None, "type": "technical"}
            for n in skill_names
        },
        "excluded_title_signals": [],
        "education_only": [],
        "context_terms": sorted({t for terms in area_rules.values() for t in terms}),
        "scoring": dict(DEFAULT_WEIGHTS),
        "queries": [q for q in (_clean(x, 80) for x in (queries or [])) if q and not q.startswith("-")]
        or [name, *list(areas)][:6],
    }
    pack = parse_pack(raw, "custom")
    directory = user_packs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{pack.id}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    _load.cache_clear()
    return pack


def active_career_id() -> str:
    """Carrera activa: ajuste guardado en la base, luego RADAR_CAREER, luego el valor por defecto."""
    try:
        from radar.settings import get_setting

        stored = get_setting("career")
    except sqlite3.Error:  # base aún inexistente
        stored = None
    return stored or os.getenv("RADAR_CAREER") or DEFAULT_CAREER


def default_pack() -> CareerPack:
    """Carrera por defecto sin tocar la base: RADAR_CAREER o Ingeniería Industrial."""
    try:
        return load_pack(os.getenv("RADAR_CAREER") or DEFAULT_CAREER)
    except CareerPackError:
        return load_pack(DEFAULT_CAREER)


def active_pack() -> CareerPack:
    try:
        return load_pack(active_career_id())
    except CareerPackError:
        return load_pack(DEFAULT_CAREER)


def normalized(names: list[str]) -> set[str]:
    return {normalize_text(n) for n in names}


def effective_weights(pack: CareerPack | None = None) -> dict[str, float]:
    """Pesos del score: los del paquete, ajustados por el usuario (`score_weights`) y normalizados."""
    pack = pack or active_pack()
    weights = dict(pack.weights)
    try:
        from radar.settings import get_json_setting

        override = get_json_setting("score_weights", {}) or {}
    except (sqlite3.Error, ValueError):
        override = {}
    for key in WEIGHT_KEYS:
        if key in override and isinstance(override[key], (int, float)) and override[key] >= 0:
            weights[key] = float(override[key])
    total = sum(weights.values())
    if total <= 0:
        return dict(pack.weights)
    return {k: v / total for k, v in weights.items()}
