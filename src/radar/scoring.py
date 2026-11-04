from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from radar.domain.models import RawJob
from radar.normalize import normalize_text
from radar.requirements import assessment, education_assessment, experience_assessment, skill_level

SCORING_VERSION = "v2.1-evidence"

DEFAULT_WEIGHTS = {
    "area": 0.30,
    "skills": 0.25,
    "seniority": 0.15,
    "education": 0.10,
    "location": 0.10,
    "preference": 0.10,
}
LEVELS = {"none": 0, "basic": 0.35, "intermediate": 0.7, "advanced": 1}


def scoring_profile(account: dict, cv: dict | None = None) -> dict:
    cv = cv or {}
    return {"areas": account.get("target_roles", account.get("areas", [])),
            "locations": account.get("locations", []), "work_modes": account.get("work_modes", []),
            "skills": account.get("skills", {}), "education": cv.get("education") or account.get("education") or [],
            "experience": cv.get("experience") or []}


def profile_fingerprint(profile, weights, market_id):
    values = {k: profile.get(k) for k in ("areas", "locations", "work_modes", "skills", "education", "experience")}
    return hashlib.sha256(json.dumps([SCORING_VERSION, values, weights, market_id], sort_keys=True, default=str).encode()).hexdigest()


def current_profile_fingerprint():
    from radar import cv_targets
    from radar.careers import active_pack, effective_weights
    from radar.db.queries import get_profile

    return profile_fingerprint(scoring_profile(get_profile() or {}, cv_targets.load_profile()),
                               effective_weights(), active_pack().id)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", text) if len(t) > 2 or t == "bi"}


def area_matches(job_area: str | None, desired_areas: set[str]) -> bool:
    """El área de la oferta coincide con lo que la persona escribió, aunque sea texto libre.

    "Procesos y mejora continua" cubre las áreas Procesos y Mejora continua; "Data/BI y reporting"
    cubre Data / BI. Coincide si el nombre del área es igual, está contenido o si todas sus palabras
    significativas aparecen en la frase.
    """
    if not job_area:
        return False
    area = normalize_text(job_area)
    area_tokens = _tokens(area)
    for phrase in desired_areas:
        if area == phrase or area in phrase or (area_tokens and area_tokens <= _tokens(phrase)):
            return True
    return False


@dataclass(slots=True)
class Score:
    total: float
    area: float
    skills: float
    seniority: float
    education: float
    location: float
    preference: float
    strong_matches: list[str]
    missing_skills: list[str]
    reason: str
    assessment: dict = field(default_factory=dict)


def score_job(
    job: RawJob,
    profile: dict,
    job_skills: set[str],
    job_area: str | None,
    weights: dict[str, float] | None = None,
) -> Score:
    w = weights or DEFAULT_WEIGHTS
    profile_skills: dict[str, str] = profile.get("skills", {})
    desired_areas = {normalize_text(x) for x in profile.get("areas", [])}
    dimensions = {}
    dimensions["area"] = assessment("unknown", "No hay área o preferencias suficientes.") if not desired_areas or not job_area else assessment(
        "met" if area_matches(job_area, desired_areas) else "missing", "Comparación con tus áreas preferidas.")
    aliases = profile.get("skill_aliases", {})
    skill_items, strong, missing = [], [], []
    for name in sorted(job_skills):
        level, quote, required = skill_level(job.description, name, aliases.get(name, ()))
        requirement = profile.get("skill_requirement_types", {}).get(name)
        if requirement in {"preferred", "desirable"}:
            required = False
        own = profile_skills.get(name)
        if own in LEVELS and own != "none":
            strong.append(name)
        if own not in LEVELS:
            item = assessment("unknown", "No declaraste un nivel; no se asume que no sepas.", quote, required)
            missing.append(name)
        elif own == "none":
            item = assessment("missing", "Declaraste no tener esta habilidad.", quote, required)
            missing.append(name)
        elif level is None:
            item = assessment("partial", "La herramienta coincide; la oferta no concreta el nivel.", quote, required)
        else:
            ratio = min(1.0, LEVELS[own] / LEVELS[level])
            item = assessment("met" if ratio == 1 else "partial", "Compara tu nivel autodeclarado con el nivel solicitado; no certifica competencia.", quote, required,
                              lower=round(ratio*100, 2), upper=round(ratio*100, 2))
            if ratio < 1:
                missing.append(name)
        skill_items.append({"name": name, "required_level": level, "declared_level": own, **item})
    if skill_items:
        denominator = sum(1 if i["required"] else 0.5 for i in skill_items)
        lower = sum(i["lower"]*(1 if i["required"] else 0.5) for i in skill_items)/denominator
        upper = sum(i["upper"]*(1 if i["required"] else 0.5) for i in skill_items)/denominator
        dimensions["skills"] = assessment("met" if lower == 100 else "unknown" if not strong else "partial",
                                          "Coincidencias de herramientas y niveles declarados.", lower=lower, upper=upper)
    else:
        dimensions["skills"] = assessment("unknown", "No hay habilidades suficientes para comparar.")
    dimensions["seniority"] = experience_assessment(job.description, profile, job_skills)
    dimensions["education"] = education_assessment(job.description, profile)
    dimensions["location"] = assessment("unknown", "No hay ubicación o preferencia suficiente.") if not profile.get("locations") or not job.location else assessment(
        "met" if any(normalize_text(x) in normalize_text(job.location) for x in profile["locations"]) else "missing", "Coincidencia geográfica aproximada; no mide tiempo de viaje.")
    dimensions["preference"] = assessment("unknown", "Modalidad o preferencia sin especificar.") if not profile.get("work_modes") or job.work_mode in {None, "unknown"} else assessment(
        "met" if job.work_mode in profile["work_modes"] else "missing", "Comparación de modalidad.")
    total = round(sum(dimensions[k]["lower"]*w[k] for k in w), 2)
    upper = round(sum(dimensions[k]["upper"]*w[k] for k in w), 2)
    coverage = round(sum(w[k]*(1-(dimensions[k]["upper"]-dimensions[k]["lower"])/100) for k in w)*100, 1)
    blockers = [k for k in ("education", "seniority") if dimensions[k]["required"] and dimensions[k]["status"] == "missing"]
    skill_gaps = [i["name"] for i in skill_items if i["required"] and
                  (i["status"] == "missing" or (i["required_level"] and i["status"] == "partial"))]
    reason = (f"Coincidencia respaldada {total:g}–{upper:g}/100; cobertura {coverage:g}%. "
              f"{len(strong)} herramientas declaradas; {len(missing)} por acreditar o reforzar. "
              + ("Requisitos no acreditados: " + ", ".join(blockers) + ". " if blockers else "")
              + "No es una probabilidad de contratación.")
    values = [dimensions[k]["lower"] for k in ("area", "skills", "seniority", "education", "location", "preference")]
    return Score(total, *values, strong, missing, reason,
                 {"version": SCORING_VERSION, "coverage": coverage, "lower_bound": total, "upper_bound": upper,
                  "dimensions": dimensions, "skills": skill_items, "unaccredited_requirements": blockers,
                  "declared_skill_gaps": skill_gaps, "academic_acceptance": dimensions["education"]["status"],
                  "eligibility": "unaccredited" if blockers else "requires_review" if any(dimensions[k]["status"] != "met" for k in ("education", "seniority")) else "declared_evidence_matches"})
