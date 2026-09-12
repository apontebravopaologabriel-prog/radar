from __future__ import annotations

from dataclasses import dataclass

from radar.domain.models import RawJob
from radar.normalize import normalize_text

LEVELS = {"none": 0, "basic": 0.35, "intermediate": 0.7, "advanced": 1}


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


def score_job(job: RawJob, profile: dict, job_skills: set[str], job_area: str | None) -> Score:
    profile_skills: dict[str, str] = profile.get("skills", {})
    desired_areas = {normalize_text(x) for x in profile.get("areas", [])}
    area = (
        100.0
        if job_area and normalize_text(job_area) in desired_areas
        else (55.0 if not desired_areas else 0.0)
    )
    strong = [
        skill
        for skill in job_skills
        if skill in profile_skills and LEVELS.get(profile_skills[skill], 0) > 0
    ]
    missing = [
        skill
        for skill in job_skills
        if skill not in profile_skills or profile_skills[skill] == "none"
    ]
    skills = 100.0 * len(strong) / len(job_skills) if job_skills else 50.0
    title = normalize_text(job.title)
    seniority = (
        100.0
        if any(x in title for x in ("practicante", "trainee", "junior", "asistente"))
        else 50.0
    )
    location = (
        100.0
        if not profile.get("locations")
        or any(normalize_text(x) in normalize_text(job.location) for x in profile["locations"])
        else 20.0
    )
    preference = (
        100.0 if profile.get("work_modes") and job.work_mode in profile["work_modes"] else 50.0
    )
    education = 70.0
    total = round(
        area * 0.30
        + skills * 0.25
        + seniority * 0.15
        + education * 0.10
        + location * 0.10
        + preference * 0.10,
        2,
    )
    reason = f"Coincide en {len(strong)} skills y tiene {len(missing)} brechas identificadas."
    return Score(
        total, area, skills, seniority, education, location, preference, strong, missing, reason
    )
